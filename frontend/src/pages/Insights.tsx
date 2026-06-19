import { useEffect, useState } from "react";
import { Table, Tabs, Select, Tag, Spin } from "antd";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import api from "../api/client";

const COLORS = ["#1a73e8", "#4caf50", "#ff9800", "#e53935", "#9c27b0", "#00bcd4", "#795548", "#607d8b"];

export default function Insights() {
  const [modules, setModules] = useState<any[]>([]);
  const [weakPoints, setWeakPoints] = useState<any[]>([]);
  const [errorDist, setErrorDist] = useState<any[]>([]);
  const [persistent, setPersistent] = useState<any[]>([]);
  const [exams, setExams] = useState<any[]>([]);
  const [compareA, setCompareA] = useState<number | null>(null);
  const [compareB, setCompareB] = useState<number | null>(null);
  const [compareData, setCompareData] = useState<any>(null);
  const [kpDetail, setKpDetail] = useState<any[]>([]);
  const [kpName, setKpName] = useState("");
  const [loading, setLoading] = useState(true);
  const [actionStats, setActionStats] = useState<any>({});

  useEffect(() => {
    Promise.all([
      api.get("/modules/summary"), api.get("/weak-points-by-type"),
      api.get("/insights/error-distribution"), api.get("/insights/persistent-weak"), api.get("/exams"),
      api.get("/insights/actionable-stats"),
    ]).then(([m, w, e, p, ex, a]) => {
      setModules(m.data); setWeakPoints(w.data); setErrorDist(e.data);
      setPersistent(p.data); setExams(ex.data);
      setActionStats(a.data); setLoading(false);
    });
  }, []);

  const compare = () => {
    if (compareA && compareB && compareA !== compareB) {
      api.get("/insights/exams-compare", { params: { a: compareA, b: compareB } }).then((r) => setCompareData(r.data));
    }
  };

  const loadKpDetail = () => {
    if (kpName) api.get("/insights/kp-detail", { params: { name: kpName } }).then((r) => setKpDetail(r.data));
  };

  if (loading) return <Spin />;

  const modChart = modules.filter((m: any) => m.total_q >= 3).map((m: any) => ({ name: m.module, 正确率: +(m.accuracy * 100).toFixed(1) }));

  return (
    <div><h2>📊 知识洞察</h2>
      <Tabs items={[
        {
          key: "action", label: "💡 行动指南",
          children: <div>
            {/* 送分题杀手 */}
            <h4>🔫 送分题杀手（全站正确率&gt;70%，但你做错了）</h4>
            {actionStats.free_kills?.length > 0 ? (
              <div>{actionStats.free_kills.map((q: any, i: number) => (
                <div key={i} style={{ marginBottom: 4, padding: "4px 8px", background: "#fff3f3", borderRadius: 4 }}>
                  <Tag color="red">全站{(q.global_ratio * 100).toFixed(0)}%</Tag>
                  {q.source?.replace(/.*?第(\d+)题/, "第$1题")} | {q.kp_names?.slice(0, 2).join("、")}
                </div>
              ))}</div>
            ) : <p style={{ color: "#999" }}>暂无。继续保持！</p>}

            {/* 不该放弃的题 */}
            <h4 style={{ marginTop: 20 }}>💸 不该放弃的题（用时&lt;10秒，全站&gt;50%）</h4>
            {actionStats.should_not_give_up?.length > 0 ? (
              <div>{actionStats.should_not_give_up.map((q: any, i: number) => (
                <div key={i} style={{ marginBottom: 4, padding: "4px 8px", background: "#fff8e1", borderRadius: 4 }}>
                  <Tag color="orange">全站{(q.global_ratio * 100).toFixed(0)}%</Tag>
                  <Tag>{q.time_sec}s</Tag>
                  {q.source?.replace(/.*?第(\d+)题/, "第$1题")} | {q.kp_names?.slice(0, 2).join("、")}
                </div>
              ))}</div>
            ) : <p style={{ color: "#999" }}>暂无。</p>}

            {/* 投入产出 Top5 */}
            <h4 style={{ marginTop: 20 }}>🎯 投入产出最高知识点 Top5</h4>
            <p style={{ color: "#666", fontSize: 13 }}>全站正确率高 + 你常错 = 最容易补的短板</p>
            {actionStats.top_roi_kps?.map((k: any, i: number) => (
              <div key={i} style={{ marginBottom: 4, padding: "4px 8px", background: "#e8f5e9", borderRadius: 4 }}>
                <strong>{k.kp}</strong> — 错{k.wrong}/{k.total}题，全站正确率{(k.avg_global * 100).toFixed(0)}%
                <span style={{ marginLeft: 8, color: "#1a73e8" }}>建议：每天做2道该类题</span>
              </div>
            ))}
          </div>
        },
        {
          key: "overview", label: "模块概览",
          children: <div>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={modChart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} /><Tooltip /><Bar dataKey="正确率" fill="#1a73e8" /></BarChart>
            </ResponsiveContainer>
            <Table dataSource={modules} rowKey="module" size="small" style={{ marginTop: 16 }}
              columns={[{ title: "模块", dataIndex: "module" }, { title: "题数", dataIndex: "total_q", width: 80 },
                { title: "正确率", width: 100, render: (_: any, r: any) => `${(r.accuracy * 100).toFixed(1)}%` },
                { title: "题型", dataIndex: "question_type", width: 100 }]} />
          </div>
        },
        {
          key: "weak", label: "薄弱题型",
          children: <Table dataSource={weakPoints} rowKey={(r: any) => r.module + r.question_type} size="small"
            columns={[
              { title: "模块", dataIndex: "module", width: 120 },
              { title: "题型", dataIndex: "question_type", width: 100 },
              { title: "总题数", dataIndex: "total", width: 80 },
              { title: "错误", dataIndex: "wrong", width: 60 },
              { title: "正确率", width: 80, render: (_: any, r: any) => `${(r.accuracy * 100).toFixed(0)}%` },
              { title: "状态", width: 80, render: (_: any, r: any) => <Tag color={r.accuracy < 0.5 ? "red" : r.accuracy < 0.7 ? "orange" : "green"}>{r.accuracy < 0.5 ? "重点补" : r.accuracy < 0.7 ? "需强化" : "正常"}</Tag> },
            ]} />
        },
        {
          key: "error-dist", label: "错误分布",
          children: <ResponsiveContainer width="100%" height={400}>
            <PieChart><Pie data={errorDist.filter((e: any) => e.error_type !== "其他")} dataKey="count" nameKey="error_type" cx="50%" cy="50%" outerRadius={140}
              label={({ error_type, count }: any) => `${error_type}(${count})`}>
              {errorDist.map((_: any, i: number) => (<Cell key={i} fill={COLORS[i % COLORS.length]} />))}</Pie><Tooltip /></PieChart>
          </ResponsiveContainer>
        },
        {
          key: "compare", label: "考试对比",
          children: <div>
            <Select placeholder="考试A" style={{ width: 200 }} value={compareA} onChange={setCompareA}
              options={exams.map((e: any) => ({ value: e.id, label: e.name.slice(0, 20) }))} />
            <Select placeholder="考试B" style={{ width: 200, marginLeft: 8 }} value={compareB} onChange={setCompareB}
              options={exams.map((e: any) => ({ value: e.id, label: e.name.slice(0, 20) }))} />
            <button onClick={compare} style={{ marginLeft: 8 }}>对比</button>
            {compareData && <Table dataSource={compareData.modules} rowKey="module" size="small" style={{ marginTop: 16 }}
              columns={[{ title: "模块", dataIndex: "module" },
                { title: compareData.exam_a?.slice(0, 10) || "A", render: (_: any, r: any) => `${(r.acc_a * 100).toFixed(0)}%` },
                { title: compareData.exam_b?.slice(0, 10) || "B", render: (_: any, r: any) => `${(r.acc_b * 100).toFixed(0)}%` },
                { title: "变化", render: (_: any, r: any) => <Tag color={r.delta > 0.03 ? "green" : r.delta < -0.03 ? "red" : "default"}>{`${(r.delta * 100).toFixed(1)}%`}</Tag> }]} />}
          </div>
        },
        {
          key: "persistent", label: "持续薄弱",
          children: <Table dataSource={persistent} rowKey="point_name" size="small"
            columns={[{ title: "知识点", dataIndex: "point_name" }, { title: "模块", dataIndex: "module", width: 100 },
              { title: "连续错", dataIndex: "streak", width: 80 },
              { title: "考试", render: (_: any, r: any) => r.exams?.map((e: any) => e.exam_name?.slice(0, 12)).join(" → ") }]} />
        },
      ]} />
    </div>
  );
}
