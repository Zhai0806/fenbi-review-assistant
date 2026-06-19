import { useEffect, useState } from "react";
import { Card, Table, Tag, Spin, Button, Tabs } from "antd";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api from "../api/client";

const LOGIC_MODS = ["言语理解与表达", "数量关系", "判断推理", "资料分析"];
const MEMORY_MODS = ["政治理论", "常识判断"];
const COLORS: Record<string, string> = { "言语理解与表达": "#1a73e8", "数量关系": "#e53935", "判断推理": "#4caf50", "资料分析": "#ff9800", "政治理论": "#9c27b0", "常识判断": "#00bcd4" };

export default function Insights() {
  const [modules, setModules] = useState<any[]>([]);
  const [exams, setExams] = useState<any[]>([]);
  const [compareA, setCompareA] = useState<number | null>(null);
  const [compareB, setCompareB] = useState<number | null>(null);
  const [compareData, setCompareData] = useState<any>(null);
  const [trendData, setTrendData] = useState<any[]>([]);
  const [contra, setContra] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [cat, setCat] = useState<"logic" | "memory">("logic");
  const activeMods = cat === "logic" ? LOGIC_MODS : MEMORY_MODS;

  useEffect(() => {
    Promise.all([
      api.get("/modules/summary"), api.get("/exams"),
      api.get("/insights/exam-trend"), api.get("/insights/contradiction"),
    ]).then(([m, ex, t, c]) => {
      setModules(m.data); setExams(ex.data);
      setTrendData(t.data || []); setContra(c.data || {}); setLoading(false);
    });
  }, []);

  const cmp = () => {
    if (compareA && compareB && compareA !== compareB)
      api.get("/insights/exams-compare", { params: { a: compareA, b: compareB } }).then(r => setCompareData(r.data));
  };

  if (loading) return <Spin />;

  const modData = modules.filter((m: any) => m.total_q >= 3 && activeMods.includes(m.module));
  const aggMods: Record<string, {total: number, correct: number}> = {};
  modData.forEach((m: any) => {
    if (!aggMods[m.module]) aggMods[m.module] = { total: 0, correct: 0 };
    aggMods[m.module].total += m.total_q;
    aggMods[m.module].correct += m.correct_q;
  });

  return (
    <div>
      <h2>📊 知识洞察</h2>
      <Button type={cat === "memory" ? "primary" : "default"}
        onClick={() => setCat(cat === "logic" ? "memory" : "logic")} style={{ marginBottom: 12 }}>
        {cat === "logic" ? "📐 逻辑模块" : "📚 知识模块"}
      </Button>
      <Tabs items={[
        {
          key: "trend", label: "趋势追踪",
          children: <div>
            <p style={{ color: "#999", fontSize: 13, marginBottom: 8 }}>
              各模块跨考正确率变化。向上的线=进步，向下的线=退步。只统计出现≥2次的模块。
            </p>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} />
                <Tooltip formatter={(v: number) => `${v.toFixed(0)}%`} />
                <Legend />
                {activeMods.map(mod => {
                  if (!trendData.some((d: any) => d[mod] !== undefined && d[mod] !== null)) return null;
                  return <Line key={mod} type="monotone" dataKey={mod} stroke={COLORS[mod] || "#999"} strokeWidth={2} dot={{ r: 4 }} connectNulls />;
                })}
              </LineChart>
            </ResponsiveContainer>
            {!trendData.length && <p style={{ color: "#999" }}>需要≥2场考试才有趋势数据</p>}
          </div>
        },
        {
          key: "compare", label: "考试对比",
          children: <div>
            <div style={{ marginBottom: 8 }}>A：{exams.slice(0, 6).map((e: any) => <Button key={e.id} size="small" type={compareA === e.id ? "primary" : "default"} onClick={() => setCompareA(e.id)} style={{ margin: 2 }}>{e.name.slice(0, 8)}</Button>)}</div>
            <div style={{ marginBottom: 8 }}>B：{exams.slice(0, 6).map((e: any) => <Button key={e.id} size="small" type={compareB === e.id ? "primary" : "default"} onClick={() => setCompareB(e.id)} style={{ margin: 2 }}>{e.name.slice(0, 8)}</Button>)}</div>
            <Button size="small" type="primary" onClick={cmp} disabled={!compareA || !compareB || compareA === compareB}>对比</Button>
            {compareData && <Table dataSource={(compareData.modules || []).filter((r: any) => activeMods.includes(r.module))} rowKey="module" size="small" style={{ marginTop: 8 }} pagination={false}
              columns={[
                { title: "模块", dataIndex: "module", width: 100 },
                { title: "A", width: 50, render: (_: any, r: any) => `${(r.acc_a * 100).toFixed(0)}%` },
                { title: "B", width: 50, render: (_: any, r: any) => `${(r.acc_b * 100).toFixed(0)}%` },
                { title: "Δ", width: 60, render: (_: any, r: any) => <Tag color={r.delta > 0.03 ? "green" : r.delta < -0.03 ? "red" : "default"}>{`${(r.delta * 100).toFixed(0)}%`}</Tag> },
              ]} />}
          </div>
        },
        {
          key: "contra", label: "矛盾分析",
          children: <div>
            {contra.principal && <div style={{ padding: 12, background: "#fff3f3", borderRadius: 8, marginBottom: 16, border: "2px solid #e53935" }}>
              <h3 style={{ color: "#e53935", margin: 0 }}>⚡ 主要矛盾：{contra.principal}</h3>
              <p style={{ marginTop: 8 }}>{contra.advice}</p>
            </div>}
            {(contra.analysis || []).map((a: any) => (
              <div key={a.module} style={{ marginBottom: 8, padding: 8, background: a.module === contra.principal ? "#fff3f3" : "#fafafa", borderRadius: 4 }}>
                <strong>{a.module}</strong> — 正确率 {a.accuracy}%
                <span style={{ marginLeft: 12, color: a.gap > 10 ? "#e53935" : "#666" }}>与最强差 {a.gap}pp</span>
                <p style={{ color: "#666", margin: "4px 0 0" }}>{a.advice}</p>
              </div>
            ))}
          </div>
        },
        {
          key: "overview", label: "总览",
          children: <div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={modData.map(m => ({ name: m.question_type || m.module, 正确率: +(m.accuracy * 100).toFixed(0) }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} />
                <Tooltip formatter={(v: number) => `${v}%`} />
                <Bar dataKey="正确率" fill="#1a73e8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <Table dataSource={modData} rowKey={(r: any) => r.module + r.question_type} size="small" pagination={false} style={{ marginTop: 12 }}
            columns={[
              { title: "模块", dataIndex: "module", width: 100 },
              { title: "题型", dataIndex: "question_type", width: 100, render: (v: string) => v || "—" },
              { title: "题数", dataIndex: "total_q", width: 60 },
              { title: "正确率", width: 70, sorter: (a: any, b: any) => a.accuracy - b.accuracy, render: (_: any, r: any) => `${(r.accuracy * 100).toFixed(0)}%` },
            ]} />
          </div>
        },
      ]} />
    </div>
  );
}
