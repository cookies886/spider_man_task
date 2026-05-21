import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  listChannels,
  createChannel,
  deleteChannel,
  testChannel,
  listRules,
  createRule,
  deleteRule,
  type ChannelType,
  type EventType,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

const CHANNEL_LABELS: Record<ChannelType, string> = {
  dingtalk: "钉钉",
  feishu: "飞书",
  wecom: "企业微信",
  email: "邮件",
}

const EVENT_LABELS: Record<EventType, string> = {
  task_failed: "任务失败",
  task_timeout: "任务超时",
  task_killed: "任务被终止",
  worker_offline: "节点掉线",
}

export function NotificationsPage() {
  const qc = useQueryClient()
  const channelsQ = useQuery({ queryKey: ["channels"], queryFn: listChannels })
  const rulesQ = useQuery({ queryKey: ["rules"], queryFn: listRules })
  const [createOpen, setCreateOpen] = useState(false)
  const [ruleOpen, setRuleOpen] = useState(false)

  const delChannel = useMutation({
    mutationFn: deleteChannel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  })
  const test = useMutation({ mutationFn: testChannel })
  const delRule = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">消息通知</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>通知渠道</span>
            <Button size="sm" onClick={() => setCreateOpen(true)}>添加渠道</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr><th className="py-2">名称</th><th>类型</th><th>状态</th><th className="text-right">操作</th></tr>
            </thead>
            <tbody>
              {channelsQ.data?.map((c) => (
                <tr key={c.id} className="border-t">
                  <td className="py-2 font-medium">{c.name}</td>
                  <td className="text-xs">{CHANNEL_LABELS[c.type]}</td>
                  <td className={`text-xs ${c.is_enabled ? "text-green-600" : "text-muted-foreground"}`}>
                    {c.is_enabled ? "启用" : "禁用"}
                  </td>
                  <td className="text-right space-x-1">
                    <Button size="sm" variant="ghost"
                      onClick={async () => {
                        try { await test.mutateAsync(c.id); toast.success("测试发送成功") }
                        catch (e: any) { toast.error("发送失败：" + (e?.response?.data?.detail || e.message)) }
                      }}>测试</Button>
                    <Button size="sm" variant="ghost" className="text-destructive"
                      onClick={() => { if (confirm(`删除 ${c.name}?`)) delChannel.mutate(c.id) }}>删除</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>通知规则</span>
            <Button size="sm" onClick={() => setRuleOpen(true)}>添加规则</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr><th className="py-2">事件</th><th>渠道</th><th className="text-right">操作</th></tr>
            </thead>
            <tbody>
              {rulesQ.data?.map((r) => {
                const ch = channelsQ.data?.find((c) => c.id === r.channel_id)
                return (
                  <tr key={r.id} className="border-t">
                    <td className="py-2">{EVENT_LABELS[r.event]}</td>
                    <td className="text-xs">{ch?.name ?? r.channel_id}</td>
                    <td className="text-right">
                      <Button size="sm" variant="ghost" className="text-destructive"
                        onClick={() => { if (confirm("删除这条规则?")) delRule.mutate(r.id) }}>删除</Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <CreateChannelDialog open={createOpen} onOpenChange={setCreateOpen}
        onCreated={() => qc.invalidateQueries({ queryKey: ["channels"] })} />
      <CreateRuleDialog open={ruleOpen} onOpenChange={setRuleOpen}
        channels={channelsQ.data ?? []}
        onCreated={() => qc.invalidateQueries({ queryKey: ["rules"] })} />
    </div>
  )
}

const TEMPLATE_VARS = [
  "{{event}}",
  "{{task_name}}",
  "{{task_id}}",
  "{{run_id}}",
  "{{exit_code}}",
  "{{error_msg}}",
  "{{node_id}}",
]

const DEFAULT_TEMPLATE_PRESETS: Record<string, string> = {
  "失败简短": "❌ {{task_name}} 失败 exit={{exit_code}}",
  "失败详细": "❌ 任务【{{task_name}}】执行失败\nrun: {{run_id}}\n退出码: {{exit_code}}\n错误: {{error_msg}}",
  "节点掉线": "⚠️ 节点 {{node_id}} 已掉线",
}

function CreateChannelDialog(p: {
  open: boolean
  onOpenChange: (o: boolean) => void
  onCreated: () => void
}) {
  const [type, setType] = useState<ChannelType>("dingtalk")
  const [name, setName] = useState("")
  const [webhook, setWebhook] = useState("")
  const [secret, setSecret] = useState("")
  const [recipients, setRecipients] = useState("")
  const [template, setTemplate] = useState("")
  const [err, setErr] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    setErr(""); setSubmitting(true)
    try {
      let config: Record<string, unknown>
      if (type === "email") config = { recipients: recipients.split(",").map((s) => s.trim()).filter(Boolean) }
      else config = { webhook, ...(secret ? { secret } : {}) }
      await createChannel({
        type,
        name,
        config,
        template: template.trim() ? template : null,
      })
      p.onCreated()
      p.onOpenChange(false)
    } catch (e: any) { setErr(e?.response?.data?.detail || e.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={p.open} onOpenChange={p.onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>添加通知渠道</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-4 gap-1">
            {(Object.keys(CHANNEL_LABELS) as ChannelType[]).map((t) => (
              <button key={t} type="button"
                className={`py-2 text-xs rounded border ${type === t ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                onClick={() => setType(t)}>
                {CHANNEL_LABELS[t]}
              </button>
            ))}
          </div>
          <Input placeholder="渠道名称" value={name} onChange={(e) => setName(e.target.value)} />
          {type === "email" ? (
            <Input placeholder="收件人列表（逗号分隔）" value={recipients}
              onChange={(e) => setRecipients(e.target.value)} />
          ) : (
            <>
              <Input placeholder="Webhook URL" value={webhook} onChange={(e) => setWebhook(e.target.value)} />
              {type === "dingtalk" && (
                <Input placeholder="加签密钥（可选）" value={secret} onChange={(e) => setSecret(e.target.value)} />
              )}
            </>
          )}
          <div className="border-t pt-3 space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">消息模板（留空使用默认）</label>
              <div className="flex gap-1">
                {Object.entries(DEFAULT_TEMPLATE_PRESETS).map(([label, tpl]) => (
                  <button
                    key={label}
                    type="button"
                    className="text-xs px-2 py-0.5 rounded border bg-muted hover:bg-muted/70"
                    onClick={() => setTemplate(tpl)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              className="w-full min-h-[80px] p-2 rounded border bg-background text-sm font-mono"
              placeholder="例如：❌ {{task_name}} 失败 exit={{exit_code}}"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            />
            <div className="text-xs text-muted-foreground">
              可用变量：
              {TEMPLATE_VARS.map((v) => (
                <button
                  key={v}
                  type="button"
                  className="mx-1 font-mono text-xs hover:text-primary"
                  onClick={() => setTemplate((s) => s + v)}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          {err && <p className="text-sm text-destructive">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => p.onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "保存中..." : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CreateRuleDialog(p: {
  open: boolean
  onOpenChange: (o: boolean) => void
  channels: { id: string; name: string }[]
  onCreated: () => void
}) {
  const [channelId, setChannelId] = useState("")
  const [event, setEvent] = useState<EventType>("task_failed")
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await createRule({ channel_id: channelId, event })
      p.onCreated()
      p.onOpenChange(false)
    } finally { setSubmitting(false) }
  }

  return (
    <Dialog open={p.open} onOpenChange={p.onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>添加通知规则</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <select className="w-full p-2 rounded border bg-background"
            value={channelId} onChange={(e) => setChannelId(e.target.value)}>
            <option value="">— 选择渠道 —</option>
            {p.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="w-full p-2 rounded border bg-background"
            value={event} onChange={(e) => setEvent(e.target.value as EventType)}>
            {(Object.keys(EVENT_LABELS) as EventType[]).map((e) => (
              <option key={e} value={e}>{EVENT_LABELS[e]}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" onClick={() => p.onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={submitting || !channelId}>
            {submitting ? "保存中..." : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
