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
      <p style={{ color: "#666" }}>📐 逻辑模块：言语、数量、判断、资料 | 📚 知识模块：政治理论、常识判断 | 复盘页可切换</p>

      <Collapse style={{ marginBottom: 16 }} items={[{
        key: "fetch", label: "📥 抓取新模考",
        children: <Space>
          <Input placeholder="URL 或 Exam Key" value={fetchInput} onChange={(e) => setFetchInput(e.target.value)} style={{ width: 300 }} />
          <Input placeholder="Cookie（可选）" value={fetchCookie} onChange={(e) => setFetchCookie(e.target.value)} type="password" />
          <Button type="primary" onClick={doFetch} loading={fetching} disabled={!fetchInput}>🚀 抓取并入库</Button>
        </Space>
      }]} />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="模考次数" value={exams.length} prefix={<FileTextOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="总题量" value={totalQ} /></Card></Col>
        <Col span={6}><Card><Statistic title="正确率" value={`${(acc * 100).toFixed(1)}%`} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="累计用时" value={`${Math.floor(totalTime / 3600)}h${Math.floor((totalTime % 3600) / 60)}m`} prefix={<ClockCircleOutlined />} /></Card></Col>
      </Row>

      {/* 艾宾浩斯复习提醒 */}
      <Card size="small" title="🔄 间隔复习提醒" style={{ marginBottom: 16 }}>
        {(() => {
          const today = new Date();
          const intervals = [1, 3, 7, 14];
          const items = intervals.map(day => {
            const target = new Date(today); target.setDate(today.getDate() - day);
            const dateStr = target.toISOString().slice(0, 10);
            const match = exams.filter((e: any) => e.date === dateStr);
            return { day, date: dateStr, count: match.length, names: match.map((e: any) => e.name?.slice(0, 15)).join(", ") };
          }).filter(x => x.count > 0);

          if (!items.length) return <p style={{ color: "#999" }}>暂无需要复习的考试。做完模考后会自动提醒。</p>;
          return items.map((x: any) => (
            <div key={x.day} style={{ marginBottom: 4, padding: "4px 8px", borderRadius: 4, background: x.day === 1 ? "#fff3f3" : x.day === 3 ? "#fff8e1" : "#f5f5f5" }}>
              <Tag color={x.day === 1 ? "red" : x.day === 3 ? "orange" : "default"}>第{x.day}天</Tag>
              {x.date} — {x.names}（{x.count}场）
            </div>
          ));
        })()}
      </Card>

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
