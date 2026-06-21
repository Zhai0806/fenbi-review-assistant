import { useEffect, useState } from "react";
import { Card, Table, Tag, Spin, Button, Tabs } from "antd";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { marked } from "marked";
import api from "../api/client";

const LOGIC_MODS = ["言语理解与表达", "数量关系", "判断推理", "资料分析"];
const MEMORY_MODS = ["政治理论", "常识判断"];
const GONGJI_MODS = ["时事政治", "政治", "经济", "管理", "公文", "人文历史", "科技地理", "法律", "农业农村知识", "其他"];
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
  const [cat, setCat] = useState<"logic" | "memory" | "gongji">("logic");
  const activeMods = cat === "logic" ? LOGIC_MODS : cat === "memory" ? MEMORY_MODS : GONGJI_MODS;

  useEffect(() => {
    Promise.all([
      api.get("/modules/summary"), api.get("/exams"),
      api.get("/insights/exam-trend"), api.get("/insights/contradiction"),
    ]).then(([m, ex, t, c]) => {
      setModules(m.data); setExams(ex.data);
      setTrendData(t.data || []); setContra(c.data || {}); setLoading(false);
    }).catch(err => {
      console.error('Insights load failed:', err);
      setLoading(false);
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
        onClick={() => setCat(cat === "logic" ? "memory" : cat === "memory" ? "gongji" : "logic")} style={{ marginBottom: 12 }}>
        {cat === "logic" ? "📐 逻辑模块" : cat === "memory" ? "📚 知识模块" : "🏛 公基"}
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
            {Object.keys(contra).filter(k => k !== "error" && typeof contra[k] === "object" && contra[k].analysis).length === 0 && !contra.error && (
              <div style={{ textAlign: "center", padding: 40, color: "#999" }}>暂无矛盾分析。请先对考试运行 AI 诊断。</div>
            )}
            {contra.error && <div style={{ color: "#999" }}>{contra.error}</div>}

            {/* 每种考试类型一个区块 */}
            {Object.entries(contra).filter(([k]) => !k.startsWith("_") && k !== "error").map(([examType, data]: [string, any]) => {
              if (!data || !data.analysis) return null;
              const isGongji = examType === "公基";
              return (
                <div key={examType} style={{ marginBottom: 24, border: `2px solid ${isGongji ? "#9c27b0" : "#1a73e8"}`, borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ padding: "8px 14px", background: isGongji ? "#f3e5f5" : "#e3f2fd", fontWeight: 600 }}>
                    {isGongji ? "🏛" : "📐"} {examType} 矛盾分析
                    {data.latest_exam && <span style={{ fontWeight: 400, color: "#666", marginLeft: 12, fontSize: 13 }}>基于：{data.latest_exam.name}（{data.latest_exam.date}）{data.latest_exam.score}</span>}
                  </div>
                  <div style={{ padding: 12 }}>

                    {/* AI 矛盾分析 */}
                    <div style={{ padding: 14, background: "#fffbf0", borderRadius: 8, marginBottom: 16, border: "2px solid #ff9800", lineHeight: 1.8 }}
                      dangerouslySetInnerHTML={{ __html: marked.parse(data.analysis, { breaks: true }) as string }} />

                    {/* 连锁影响（仅行测/职测） */}
                    {(data.cascade || []).length > 0 && <div style={{ marginBottom: 16 }}>
                      <h4 style={{ color: "#e53935" }}>⚠️ 连锁影响</h4>
                      {data.cascade.map((c: any, i: number) => (
                        <div key={i} style={{ padding: 8, marginBottom: 6, background: "#fff3f3", borderRadius: 6, border: "1px solid #ffcdd2" }}>
                          <div><strong>{c["超时模块"]}</strong> 超时 {c["超时倍数"]} 倍（正确率仅{c["正确率"]}%）</div>
                          <div style={{ marginTop: 4 }}>挤压了：{c["可能挤压的模块"]?.map((m: string) => <Tag key={m} color="red" style={{ marginLeft: 4 }}>{m}</Tag>)}</div>
                          {c["分析"] && <div style={{ marginTop: 4, color: "#888", fontSize: 12 }}>{c["分析"]}</div>}
                        </div>
                      ))}
                    </div>}

                    {/* 题型粒度分析表 */}
                    {data.qtype_detail && data.qtype_detail.length > 0 && <div style={{ marginBottom: 16 }}>
                      <h4>题型粒度分析</h4>
                      <Table dataSource={data.qtype_detail} rowKey={(r: any) => r["模块"] + r["题型"]} size="small" pagination={false}
                        columns={[
                          { title: "模块", dataIndex: "模块", width: 100 },
                          { title: "题型", dataIndex: "题型", width: 100 },
                          { title: "题数", dataIndex: "题数", width: 50 },
                          { title: "你的", dataIndex: "你的正确率", width: 60, render: (v: number) => `${v}%` },
                          { title: "全站", dataIndex: "全站正确率", width: 60, render: (v: any) => v != null ? `${v}%` : "?" },
                          { title: "差距", dataIndex: "差距", width: 60, render: (v: any) => v != null ? <span style={{ color: v < -10 ? "#e53935" : v > 10 ? "#4caf50" : "#666" }}>{v > 0 ? "+" : ""}{v}pp</span> : "?" },
                          { title: "判定", dataIndex: "判定", width: 80, render: (v: string) => <Tag color={v === "个人弱" ? "red" : v === "题目难" ? "orange" : "default"}>{v}</Tag> },
                        ]} />
                    </div>}

                    {/* 跨考试趋势 */}
                    {data.trends && data.trends.length > 0 && <div style={{ marginBottom: 16 }}>
                      <h4>跨考试演化趋势</h4>
                      {data.trends.map((t: any, i: number) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, padding: "4px 8px", background: "#fafafa", borderRadius: 4 }}>
                          <strong style={{ width: 100 }}>{t["模块"]}</strong>
                          <span style={{ flex: 1, fontSize: 12, color: "#666" }}>{(t["趋势"] || []).map((p: any) => `${p["考试"]} ${p["正确率"]}%`).join(" → ")}</span>
                          <Tag color={t["方向"] === "↑提升" ? "green" : t["方向"] === "↓下降" ? "red" : "default"}>{t["方向"]} {t["变化"]}%</Tag>
                        </div>
                      ))}
                    </div>}

                    {/* 用时矩阵 */}
                    {data.timing_matrix && data.timing_matrix.length > 0 && <div>
                      <h4>用时-正确率矩阵</h4>
                      <Table dataSource={data.timing_matrix} rowKey="模块" size="small" pagination={false}
                        columns={[
                          { title: "#", dataIndex: "序号", width: 40 },
                          { title: "模块", dataIndex: "模块", width: 100 },
                          { title: "题数", dataIndex: "题数", width: 50 },
                          { title: "正确率", dataIndex: "正确率", width: 70, render: (v: number) => `${v}%` },
                          { title: "平均用时", dataIndex: "平均用时秒", width: 70, render: (v: number) => `${v}秒` },
                          { title: "预算", dataIndex: "预算秒", width: 60, render: (v: number) => `${v}秒` },
                          { title: "超支", dataIndex: "超支比例", width: 70, render: (v: number) => <span style={{ color: v > 1.3 ? "#e53935" : v > 1.1 ? "#ff9800" : "#4caf50" }}>{v.toFixed(1)}x</span> },
                        ]} />
                    </div>}
                  </div>
                </div>
              );
            })}
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
