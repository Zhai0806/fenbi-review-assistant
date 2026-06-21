import { useEffect, useState } from "react";
import { Tabs, Input, Button, List, Card, Popconfirm, message, Space, Spin } from "antd";
import { FileTextOutlined } from "@ant-design/icons";
import { marked } from "marked";
import api from "../api/client";

export default function Notes() {
  const [notes, setNotes] = useState<any[]>([]);
  const [links, setLinks] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [reportContent, setReportContent] = useState("");
  const [reportLoading, setReportLoading] = useState(false);
  const [ntitle, setNtitle] = useState("");
  const [ncontent, setNcontent] = useState("");
  const [lname, setLname] = useState("");
  const [lurl, setLurl] = useState("");
  const [ldesc, setLdesc] = useState("");

  useEffect(() => {
    api.get("/notes").then((r) => setNotes(r.data));
    api.get("/links").then((r) => setLinks(r.data));
    api.get("/reports").then((r) => setReports(r.data));
  }, []);

  const loadReport = async (name: string) => {
    setReportLoading(true);
    const r = await api.get(`/reports/${encodeURIComponent(name)}`);
    setReportContent(r.data.content || "");
    setReportLoading(false);
  };

  const addNote = async () => {
    if (!ntitle) return;
    await api.post("/notes", { title: ntitle, content: ncontent });
    setNtitle(""); setNcontent("");
    const r = await api.get("/notes"); setNotes(r.data);
    message.success("已保存");
  };

  const delNote = async (id: number) => {
    await api.delete(`/notes/${id}`);
    setNotes(notes.filter((n) => n.id !== id));
  };

  const addLink = async () => {
    if (!lname || !lurl) return;
    await api.post("/links", { name: lname, url: lurl, desc: ldesc });
    setLname(""); setLurl(""); setLdesc("");
    const r = await api.get("/links"); setLinks(r.data);
  };

  const delLink = async (i: number) => {
    await api.delete(`/links/${i}`);
    setLinks(links.filter((_, j) => j !== i));
  };

  return (
    <div>
      <h2>📝 笔记链接</h2>
      <Tabs items={[
        {
          key: "notes", label: "📝 笔记",
          children: <div>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Input placeholder="标题" value={ntitle} onChange={(e) => setNtitle(e.target.value)} />
              <Input.TextArea rows={4} placeholder="内容" value={ncontent} onChange={(e) => setNcontent(e.target.value)} />
              <Button type="primary" onClick={addNote}>保存笔记</Button>
            </Space>
            <List dataSource={notes} style={{ marginTop: 16 }}
              renderItem={(n: any) => (
                <Card size="small" style={{ marginBottom: 8 }} title={n.title}
                  extra={<Popconfirm title="删除?" onConfirm={() => delNote(n.id)}><Button size="small" danger>删除</Button></Popconfirm>}>
                  <p style={{ whiteSpace: "pre-wrap" }}>{n.content}</p>
                  <small style={{ color: "#999" }}>{n.updated_at || n.created_at}</small>
                </Card>
              )} />
          </div>
        },
        {
          key: "links", label: "🔗 链接",
          children: <div>
            <Space style={{ marginBottom: 8 }}>
              <Input placeholder="名称" value={lname} onChange={(e) => setLname(e.target.value)} />
              <Input placeholder="URL" value={lurl} onChange={(e) => setLurl(e.target.value)} />
              <Input placeholder="备注" value={ldesc} onChange={(e) => setLdesc(e.target.value)} />
              <Button onClick={addLink}>添加</Button>
            </Space>
            <List dataSource={links}
              renderItem={(l: any, i: number) => (
                <List.Item actions={[<Button key="del" size="small" danger onClick={() => delLink(i)}>删除</Button>]}>
                  <a href={l.url} target="_blank" rel="noopener noreferrer">{l.name}</a>
                  {l.desc && <span style={{ color: "#999", marginLeft: 8 }}>{l.desc}</span>}
                </List.Item>
              )} />
          </div>
        },
        {
          key: "reports", label: "📊 报告",
          children: <div style={{ display: "flex", gap: 16, height: "calc(100vh - 200px)" }}>
            <div style={{ width: 260, borderRight: "1px solid #eee", overflow: "auto" }}>
              <List dataSource={reports} size="small"
                renderItem={(r: any) => (
                  <List.Item style={{ cursor: "pointer", padding: "6px 8px" }}
                    onClick={() => loadReport(r.name)}>
                    <FileTextOutlined style={{ marginRight: 8 }} />
                    <span style={{ fontSize: 13 }}>{r.name.replace('.md', '')}</span>
                  </List.Item>
                )} />
            </div>
            <div style={{ flex: 1, overflow: "auto" }}>
              {reportLoading ? <Spin /> : (
                reportContent ? (
                  <div dangerouslySetInnerHTML={{ __html: marked.parse(reportContent, { breaks: true }) as string }} />
                ) : (
                  <div style={{ color: "#999", textAlign: "center", padding: 40 }}>点击左侧文件名查看报告</div>
                )
              )}
            </div>
          </div>
        },
      ]} />
    </div>
  );
}
