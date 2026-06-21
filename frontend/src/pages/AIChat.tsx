import { useEffect, useState, useRef } from "react";
import { Input, Button, List, Select, Space, message, Spin, Card } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { marked } from "marked";
import api from "../api/client";

export default function AIChat() {
  const [convs, setConvs] = useState<any[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api.get("/chat/conversations").then(async (r) => {
      const cs = r.data;
      setConvs(cs);
      const active = cs.find((c: any) => c.active) || cs[0];
      if (active) {
        setActiveId(active.id);
        // Load messages for the active conversation
        const mr = await api.post(`/chat/conversations/${active.id}/activate`);
        setMessages(mr.data.messages || []);
      }
    });
  }, []);

  const loadMessages = (cid: string) => {
    api.get(`/chat/conversations`).then((r) => {
      setConvs(r.data);
    });
  };

  const send = async () => {
    if (!input.trim() || !activeId) return;
    setLoading(true);
    setMessages((m) => [...m, { role: "user", content: input }]);
    const q = input; setInput("");
    const controller = new AbortController();
    chatAbortRef.current = controller;
    try {
      const r = await api.post("/chat/send", { query: q }, { signal: controller.signal });
      setMessages(r.data.messages);
    } catch (e: any) {
      if (e.name === 'CanceledError' || e.code === 'ERR_CANCELED') {
        // 用户主动取消，消息已保存到后端，刷新即可
      } else {
        message.error(e?.response?.data?.detail || "发送失败");
      }
    }
    setLoading(false);
    chatAbortRef.current = null;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const cancelSend = () => {
    chatAbortRef.current?.abort();
  };

  const newConv = async () => {
    const name = prompt("会话名称：") || "新对话";
    await api.post("/chat/conversations", { name });
    const r = await api.get("/chat/conversations");
    setConvs(r.data);
    const active = r.data.find((c: any) => c.active);
    if (active) { setActiveId(active.id); setMessages([]); }
  };

  const switchConv = async (cid: string) => {
    const r = await api.post(`/chat/conversations/${cid}/activate`);
    setActiveId(cid);
    setMessages(r.data.messages || []);
  };

  const delConv = async (cid: string) => {
    await api.delete(`/chat/conversations/${cid}`);
    const r = await api.get("/chat/conversations");
    setConvs(r.data);
    if (activeId === cid) {
      const a = r.data[0];
      if (a) { setActiveId(a.id); setMessages([]); }
    }
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 120px)" }}>
      <div style={{ width: 220, borderRight: "1px solid #eee", padding: 8 }}>
        <Button icon={<PlusOutlined />} block onClick={newConv}>新对话</Button>
        <List dataSource={convs} style={{ marginTop: 8 }} size="small"
          renderItem={(c: any) => (
            <List.Item style={{ cursor: "pointer", background: c.id === activeId ? "#e6f4ff" : "transparent", padding: "4px 8px", borderRadius: 4 }}
              onClick={() => switchConv(c.id)}
              actions={[<DeleteOutlined key="del" onClick={(e) => { e.stopPropagation(); delConv(c.id); }} />]}>
              {c.name}
            </List.Item>
          )} />
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "0 16px" }}>
        <div style={{ flex: 1, overflow: "auto", paddingBottom: 16 }}>
          {messages.map((m: any, i: number) => (
            <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", margin: "8px 0" }}>
              <div style={{ maxWidth: "70%", padding: "8px 14px", borderRadius: 16,
                background: m.role === "user" ? "#1a73e8" : "#f0f2f6",
                color: m.role === "user" ? "#fff" : "#333",
                borderBottomRightRadius: m.role === "user" ? 4 : 16,
                borderBottomLeftRadius: m.role === "user" ? 16 : 4,
              }}>
                {m.role === "user" ? m.content : (
                  <div dangerouslySetInnerHTML={{ __html: marked.parse(m.content, { breaks: true }) as string }} />
                )}
              </div>
            </div>
          ))}
          {loading && <Spin />}
          <div ref={bottomRef} />
        </div>
        <div style={{ padding: "8px 0", borderTop: "1px solid #eee" }}>
          <Space.Compact style={{ width: "100%" }}>
            <Input.TextArea value={input} onChange={(e) => setInput(e.target.value)}
              onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="输入问题...（Enter发送，Shift+Enter换行）"
              autoSize={{ minRows: 1, maxRows: 6 }}
              style={{ resize: 'none' }} />
            {loading ? (
              <Button danger onClick={cancelSend}>停止</Button>
            ) : (
              <Button type="primary" onClick={send}>发送</Button>
            )}
          </Space.Compact>
        </div>
      </div>
    </div>
  );
}
