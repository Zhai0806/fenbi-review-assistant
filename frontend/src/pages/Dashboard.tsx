import { useEffect, useState } from "react";
import { Card, Row, Col, Statistic, Table, Tag, Input, Button, Collapse, message, Space } from "antd";
import { FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined, DownloadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

export default function Dashboard() {
  const [exams, setExams] = useState<any[]>([]);
  const [fetchInput, setFetchInput] = useState("");
  const [fetchCookie, setFetchCookie] = useState("");
  const [fetching, setFetching] = useState(false);
  const nav = useNavigate();

  useEffect(() => { api.get("/exams").then((r) => setExams(r.data)); }, []);

  const doFetch = async () => {
    if (!fetchInput) return;
    setFetching(true);
    try {
      const r = await api.post("/exams/fetch", { input: fetchInput, cookie: fetchCookie });
      if (r.data.success) {
        message.success(`${r.data.exam_name?.slice(0, 30)} — ${r.data.total_q}题`);
        api.get("/exams").then((r) => setExams(r.data));
        setFetchInput("");
      } else {
        message.error(r.data.error || "抓取失败");
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "抓取失败");
    }
    setFetching(false);
  };

  const totalQ = exams.reduce((s, e) => s + e.total, 0);
  const totalC = exams.reduce((s, e) => s + e.correct, 0);
  const totalTime = exams.reduce((s, e) => s + e.time_sec, 0);
  const acc = totalQ > 0 ? totalC / totalQ : 0;

  return (
    <div>
      <h2>📋 仪表盘</h2>

      <Collapse style={{ marginBottom: 16 }} items={[{
        key: "fetch", label: "📥 抓取新模考",
        children: <Space>
          <Input placeholder="URL 或 Exam Key" value={fetchInput} onChange={(e) => setFetchInput(e.target.value)} style={{ width: 300 }} />
          <Input placeholder="Cookie（可选）" value={fetchCookie} onChange={(e) => setFetchCookie(e.target.value)} type="password" />
          <Button type="primary" onClick={doFetch} loading={fetching} disabled={!fetchInput}>🚀 抓取并入库</Button>
        </Space>
      }]} />

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}><Card><Statistic title="模考次数" value={exams.length} prefix={<FileTextOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="总题量" value={totalQ} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="正确率" value={`${(acc * 100).toFixed(1)}%`} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="累计用时" value={`${Math.floor(totalTime / 3600)}h${Math.floor((totalTime % 3600) / 60)}m`} prefix={<ClockCircleOutlined />} /></Card></Col>
      </Row>

      <h3>模考记录</h3>
      <Table dataSource={exams} rowKey="id" size="small"
        onRow={(r) => ({ onClick: () => nav(`/exam/${r.id}`), style: { cursor: "pointer" } })}
        columns={[
          { title: "日期", dataIndex: "date", width: 120 },
          { title: "试卷", dataIndex: "name", ellipsis: true },
          { title: "题量", dataIndex: "total", width: 80 },
          { title: "正确率", width: 100, render: (_: any, r: any) => <Tag color={r.correct / r.total > 0.65 ? "green" : "orange"}>{(r.correct / r.total * 100).toFixed(0)}%</Tag> },
          { title: "类型", dataIndex: "type", width: 80 },
        ]}
      />
    </div>
  );
}
