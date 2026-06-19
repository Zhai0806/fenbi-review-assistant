import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Select, Button, Tag, Space, message } from "antd";
import { OrderedListOutlined, FileTextOutlined, SearchOutlined } from "@ant-design/icons";
import api from "../api/client";

const MOD_ORDER = ["政治理论", "常识判断", "言语理解与表达", "数量关系", "判断推理", "资料分析"];
const errorTypes = ["计算失误", "公式用错", "概念混淆", "审题不清", "时间不足蒙的", "记忆盲区", "放弃", "其他"];

function idxToL(i: string | number) {
  return { "0": "A", "1": "B", "2": "C", "3": "D" }[String(i)] || String(i);
}

export default function ExamReview() {
  const nav = useNavigate();
  const [exams, setExams] = useState<any[]>([]);
  const [examId, setExamId] = useState(0);
  const [exam, setExam] = useState<any>(null);
  const [showCard, setShowCard] = useState(false);
  const [showDiagCard, setShowDiagCard] = useState(false);
  const [noteKeys, setNoteKeys] = useState<Record<string, boolean>>({});
  const [pDiags, setPDiags] = useState<any[]>([]);
  const [diagnosing, setDiagnosing] = useState(false);
  const [viewMode, setViewMode] = useState<"review" | "diagnose">("review");
  const qRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const diagRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    api.get("/exams").then(r => { setExams(r.data); if (r.data.length) setExamId(r.data[0].id); });
  }, []);
  useEffect(() => {
    if (!examId) return; nav(`/exam/${examId}`, { replace: true });
    Promise.all([api.get(`/exams/${examId}`), api.get("/diagnoses", { params: { exam_id: examId } })]).then(([e, d]) => {
      setExam(e.data); setPDiags(d.data);
    });
  }, [examId]);

  const runDiagnose = async () => {
    setDiagnosing(true); await api.post(`/diagnose/${examId}`);
    setDiagnosing(false);
    api.get("/diagnoses", { params: { exam_id: examId } }).then(r => setPDiags(r.data));
    api.get(`/exams/${examId}`).then(r => setExam(r.data));
    message.success("诊断完成");
  };
  const confirmDiag = (diagId: number, et?: string) => {
    api.post(`/diagnoses/${diagId}/confirm`, { error_type: et }).then(() => {
      api.get("/diagnoses", { params: { exam_id: examId } }).then(r => setPDiags(r.data));
      api.get(`/exams/${examId}`).then(r => setExam(r.data));
    });
  };
  const scrollTo = (key: string) => { setShowCard(false); setTimeout(() => qRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "center" }), 100); };

  if (!exam) return null;

  const qs: any[] = exam.questions || [];
  const mats = exam.materials || [];
  const matByGid: Record<string, any> = {}; mats.forEach((m: any) => matByGid[m.globalId] = m);
  const diagMap: Record<string, any> = {}; pDiags.forEach((d: any) => diagMap[d.question_key] = d);
  const hasDiag = (q: any) => !!diagMap[q.key] || (q.error_type && q.error_type !== "其他");
  const hasNote = (q: any) => !!(q.user_note && q.user_note.trim());

  const modQs: Record<string, any[]> = {};
  MOD_ORDER.forEach(m => modQs[m] = []);
  qs.forEach((q: any) => {
    const mod = MOD_ORDER.includes(q.module) ? q.module : "其他";
    if (!modQs[mod]) modQs[mod] = [];
    modQs[mod].push(q);
  });
  Object.values(modQs).forEach(arr => arr.forEach((q: any, i: number) => q._mi = i + 1));

  // 资料分析分组
  const matGroups: Record<string, any[]> = {};
  (modQs["资料分析"] || []).forEach((q: any) => {
    (q.materialKeys || []).forEach((mk: string) => {
      if (!matGroups[mk]) matGroups[mk] = [];
      matGroups[mk].push(q);
    });
  });

  return (
    <div style={{ maxWidth: "100%", textAlign: "left" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Select value={examId} onChange={setExamId} style={{ width: 380 }}
          options={exams.map((e: any) => ({ value: e.id, label: `${e.name?.slice(0, 40)} (${e.date})` }))} />
        <Space>
          <Button icon={<FileTextOutlined />} type={viewMode === "review" ? "primary" : "default"} onClick={() => setViewMode("review")}>题目浏览</Button>
          <Button icon={<SearchOutlined />} type={viewMode === "diagnose" ? "primary" : "default"} onClick={() => setViewMode("diagnose")}>
            诊断总览{pDiags.length > 0 && <Tag color="red" style={{ marginLeft: 4 }}>{pDiags.length}</Tag>}
          </Button>
          <Button loading={diagnosing} onClick={runDiagnose} size="small">{pDiags.length > 0 ? "重新诊断" : "🤖 AI诊断"}</Button>
        </Space>
      </div>

      {/* 诊断总览 */}
      {viewMode === "diagnose" && (
        pDiags.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "#999" }}>
            <p>暂无 AI 诊断。</p>
            <Button type="primary" onClick={runDiagnose} loading={diagnosing}>🤖 开始 AI 诊断</Button>
          </div>
        ) : (
          MOD_ORDER.map(mod => {
            const md = pDiags.filter((d: any) => qs.find((q: any) => q.key === d.question_key)?.module === mod);
            if (!md.length) return null;
            return (
              <div key={mod} style={{ marginBottom: 16 }}>
                <h3 style={{ fontSize: 16, borderBottom: "2px solid #1a73e8", paddingBottom: 4 }}>{mod} ({md.length}条)</h3>
                {md.map((d: any) => {
                  const q = qs.find((q: any) => q.key === d.question_key);
                  const mks = q?.materialKeys || [];
                  const hasMat = mks.length > 0 && mks.some((mk: string) => matByGid[mk]);
                  return (
                    <div key={d.id} ref={el => diagRefs.current[d.id] = el} style={{ marginBottom: 8, padding: 10, background: "#f9f9f9", borderRadius: 6 }}>
                      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: q ? 8 : 0 }}>
                        <Tag color={d.confidence > 0.7 ? "red" : "orange"}>{d.error_type}</Tag>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600 }}>{d.source?.replace(/.*?第(\d+)题/, "第$1题") || d.question_key?.slice(-8)}
                            {q?.raw_content && <span style={{ color: "#999", marginLeft: 8, fontSize: 13 }}>{q.raw_content?.replace(/<[^>]+>/g, "").slice(0, 60)}...</span>}
                          </div>
                          <div style={{ color: "#666" }}>💬 {d.specific_error || d.explanation}</div>
                          <div>🖊 {idxToL(d.your_answer)} | ✅ {idxToL(d.correct_answer)} | {(d.confidence * 100).toFixed(0)}%</div>
                        </div>
                        <Space>
                          <Select size="small" value={d.error_type} style={{ width: 120 }}
                            options={errorTypes.map(t => ({ value: t, label: t }))}
                            onChange={v => confirmDiag(d.id, v)} />
                          <Button size="small" type="primary" onClick={() => confirmDiag(d.id, d.error_type)}>确认</Button>
                        </Space>
                      </div>
                      {q && (
                        <div style={{ marginTop: 8, padding: 8, background: "#fff", borderRadius: 4, border: "1px solid #eee", display: "flex", gap: 16 }}>
                          {hasMat && (<div style={{ flex: 1.5, background: "#f5f5f5", padding: 10, borderRadius: 4, fontSize: 13, lineHeight: 1.8 }}>{mks.map((mk: string) => { const m = matByGid[mk]; return m ? <div key={mk} dangerouslySetInnerHTML={{ __html: m.content?.replace(/src="\/\//g, 'src="https://') }} /> : null; })}</div>)}
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 14, marginBottom: 4 }} dangerouslySetInnerHTML={{ __html: (q.raw_content || "").replace(/src="\/\//g, 'src="https://') }} />
                            {(q.raw_options || []).map((opt: string, oi: number) => {
                              const plain = (opt || "").replace(/<[^>]+>/g, "").trim();
                              const isF = /<img/.test(opt || "");
                              return (<span key={oi} style={{ display: "inline-block", margin: "2px 8px 2px 0", padding: "2px 6px", borderRadius: 3, fontSize: 13, background: String(q.your_answer) === String(oi) ? "#fce4ec" : String(q.correct_answer) === String(oi) ? "#e8f5e9" : "transparent", border: String(q.correct_answer) === String(oi) ? "1px solid #4caf50" : "1px solid transparent" }}>{idxToL(oi)}. {isF ? <span dangerouslySetInnerHTML={{ __html: opt.replace(/src="\/\//g, 'src="https://') }} /> : plain}</span>);
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })
        )
      )}

      {/* 题目浏览 */}
      {viewMode === "review" && MOD_ORDER.map(mod => {
        const mq = modQs[mod] || [];
        if (!mq.length) return null;
        if (mod === "资料分析") {
          return (<div key={mod} style={{ marginBottom: 24 }}>
            <h3 style={{ borderBottom: "2px solid #1a73e8", paddingBottom: 4, fontSize: 18, textAlign: "left", marginBottom: 12 }}>{mod}</h3>
            {Object.entries(matGroups).map(([mk, gqs]) => {
            const mat = matByGid[mk];
            gqs.forEach((q: any, i: number) => q._gi = i + 1);
            return (
              <div key={mk} style={{ display: "flex", gap: 12, marginBottom: 24 }}>
                <div style={{ flex: 1.5, background: "#fafafa", padding: 12, borderRadius: 6, fontSize: 14, lineHeight: 2, height: "80vh", overflow: "auto" }}
                  dangerouslySetInnerHTML={{ __html: (mat?.content || "").replace(/src="\/\//g, 'src="https://') }} />
                <div style={{ flex: 1, overflow: "auto", height: "80vh" }}>
                  {gqs.map((q: any) => <div key={q.key} ref={el => qRefs.current[q.key] = el}>{Q(q, noteKeys, setNoteKeys, diagMap, hasNote)}</div>)}
                </div>
              </div>
            );
          })}
          </div>);
        }
        return (
          <div key={mod} style={{ marginBottom: 24 }}>
            <h3 style={{ borderBottom: "2px solid #1a73e8", paddingBottom: 4, fontSize: 18, textAlign: "left" }}>{mod}</h3>
            {mq.map((q: any) => <div key={q.key} ref={el => qRefs.current[q.key] = el}>{Q(q, noteKeys, setNoteKeys, diagMap, hasNote)}</div>)}
          </div>
        );
      })}

      {/* 题目页答题卡 */}
      {viewMode === "review" && (<>
        <div style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", zIndex: 100 }}>
          <Button type="primary" shape="round" icon={<OrderedListOutlined />} onClick={() => setShowCard(true)} size="large">答题卡</Button>
        </div>
        <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 1000, background: "#fff", borderTop: "2px solid #1a73e8", padding: "16px 24px", maxHeight: "50vh", overflow: "auto",
          transform: showCard ? "translateY(0)" : "translateY(100%)", transition: "transform 0.3s ease-in-out", boxShadow: "0 -4px 20px rgba(0,0,0,0.15)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}><strong>答题卡</strong><span style={{ cursor: "pointer", color: "#999" }} onClick={() => setShowCard(false)}>✕ 收起</span></div>
        {MOD_ORDER.map(mod => {
          const mq2 = modQs[mod] || [];
          if (!mq2.length) return null;
          if (mod === "资料分析") {
            const gs: Record<string, any[]> = {};
            mq2.forEach((q: any) => (q.materialKeys || []).forEach((mk: string) => { if (!gs[mk]) gs[mk] = []; gs[mk].push(q); }));
            const noM = mq2.filter((q: any) => !(q.materialKeys || []).length);
            return (
              <div key={mod} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#666", marginBottom: 4 }}>{mod}</div>
                {Object.entries(gs).map(([mk, gqs], gi) => (
                  <div key={mk} style={{ marginBottom: 4 }}>
                    {Object.keys(gs).length > 1 && <span style={{ fontSize: 11, color: "#999" }}>材料{gi + 1} </span>}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {gqs.map((q: any, i: number) => numBox(q, i + 1, scrollTo, hasDiag, hasNote))}
                    </div>
                  </div>
                ))}
                {noM.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{noM.map((q: any) => numBox(q, q._mi, scrollTo, hasDiag, hasNote))}</div>}
              </div>
            );
          }
          return (
            <div key={mod} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#666", marginBottom: 4 }}>{mod}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{mq2.map((q: any) => numBox(q, q._mi, scrollTo, hasDiag, hasNote))}</div>
            </div>
          );
        })}
      </div>
      </> )}

      {/* 诊断页答题卡 */}
      {viewMode === "diagnose" && pDiags.length > 0 && (<>
        <div style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", zIndex: 100 }}>
          <Button type="primary" shape="round" icon={<OrderedListOutlined />} onClick={() => setShowDiagCard(true)} size="large">错题卡 ({pDiags.length})</Button>
        </div>
        {showDiagCard && (<div style={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 1000, background: "#fff", borderTop: "2px solid #e53935", padding: "16px 24px", maxHeight: "50vh", overflow: "auto", boxShadow: "0 -4px 20px rgba(0,0,0,0.15)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}><strong>诊断错题卡</strong><span style={{ cursor: "pointer", color: "#999" }} onClick={() => setShowDiagCard(false)}>✕ 收起</span></div>
          {MOD_ORDER.map(mod => {
            const md = pDiags.filter((d: any) => qs.find((q: any) => q.key === d.question_key)?.module === mod);
            if (!md.length) return null;
            return (<div key={mod} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#666", marginBottom: 4 }}>{mod}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {md.map((d: any) => (<span key={d.id} onClick={() => { setShowDiagCard(false); setTimeout(() => diagRefs.current[d.id]?.scrollIntoView({ behavior: "smooth", block: "center" }), 100); }}
                  style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", width: 32, height: 32, borderRadius: 6, fontSize: 13, fontWeight: 600,
                    background: "#fce4ec", color: "#e53935", border: "1px solid #e53935" }}>{(() => { const fq = qs.find((q: any) => q.key === d.question_key); return fq?._mi || "?"; })()}</span>))}
              </div>
            </div>);
          })}
        </div>)}
      </> )}

    </div>
  );
}

function numBox(q: any, i: number, scrollTo: any, hasDiag: any, hasNote: any) {
  const unanswered = !q.your_answer || q.your_answer === "" || q.status === 0;
  const color = unanswered ? "#bbb" : q.is_correct ? "#4caf50" : "#e53935";
  const bg = unanswered ? "#f5f5f5" : q.is_correct ? "#e8f5e9" : "#fce4ec";
  return (
    <span key={q.key} onClick={() => scrollTo(q.key)} style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", width: 32, height: 32, borderRadius: 6, fontSize: 13, fontWeight: 600, background: bg, color, border: `1px solid ${color}` }}>
      {i}{hasDiag(q) ? "·" : ""}{hasNote(q) ? "✎" : ""}
    </span>
  );
}

function Q(q: any, noteKeys: Record<string, boolean>, setNoteKeys: any, diagMap: Record<string, any>, hasNote: (q: any) => boolean) {
  const wrong = !q.is_correct;
  const correct = String(q.correct_answer);
  const yours = String(q.your_answer);
  return (
    <div id={q.key} style={{ marginBottom: 20, padding: "12px 0", borderBottom: "1px solid #eee", textAlign: "left" }}>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
        <span style={{ marginRight: 8 }}>{q.is_correct ? "✅" : "❌"}</span>第{q._gi || q._mi || "?"}题
        {wrong && <Tag color="red" style={{ marginLeft: 8 }}>{q.error_type || "未标注"}</Tag>}
        {diagMap[q.key] && <Tag color="blue" style={{ marginLeft: 4 }}>🤖 AI已诊断</Tag>}
        {hasNote(q) && <span style={{ fontSize: 12, color: "#999", marginLeft: 4 }}>📝</span>}
      </div>
      <div style={{ fontSize: 15, marginBottom: 8, lineHeight: 1.8 }}
        dangerouslySetInnerHTML={{ __html: (q.raw_content || "").replace(/src="\/\//g, 'src="https://') }} />
      <div style={{ marginBottom: 4 }}>{(q.raw_options || []).map((opt: string, oi: number) => {
        const isY = yours === String(oi), isC = correct === String(oi);
        const plain = (opt || "").replace(/<[^>]+>/g, "").trim();
        const isFormula = /<img/.test(opt || "");
        return (<span key={oi} style={{ display: "inline-block", margin: "2px 16px 2px 0", padding: "3px 10px", borderRadius: 4, fontSize: 14, background: isY ? (q.is_correct ? "#e8f5e9" : "#fce4ec") : "transparent", border: isC ? "1px solid #4caf50" : "1px solid transparent", fontWeight: isY ? 700 : 400 }}>
          {idxToL(oi)}. {isFormula ? <span dangerouslySetInnerHTML={{ __html: opt.replace(/src="\/\//g, 'src="https://') }} /> : plain}
          {isY ? " ←" : ""}{isC && !isY ? " ✅" : ""}
        </span>);
      })}</div>
      <div style={{ display: "flex", gap: 24, fontSize: 14, color: "#555", marginTop: 6, flexWrap: "wrap" }}>
        <span>✅ 正确：{idxToL(correct)}</span><span>🖊 你的：{idxToL(yours)}</span><span>⏱ {q.time_sec || "-"}s</span>
        {wrong && <span>📊 全站：{((q.global_ratio || 0) * 100).toFixed(0)}%</span>}
        <span style={{ cursor: "pointer", color: "#1a73e8" }} onClick={() => setNoteKeys({ ...noteKeys, [q.key]: !noteKeys[q.key] })}>📝 笔记</span>
      </div>
      {noteKeys[q.key] && (
        <div style={{ marginTop: 8, padding: 8, background: "#fafafa", borderRadius: 6 }}>
          <input placeholder="笔记标题" defaultValue={q.source?.slice(0, 25) || "错题"} style={{ width: "100%", padding: "4px 8px", fontSize: 14, marginBottom: 4, border: "1px solid #ddd", borderRadius: 4 }} id={`nt_${q.key}`} />
          <textarea defaultValue={q.user_note || ""} placeholder="笔记内容..." rows={3} style={{ width: "100%", padding: "4px 8px", fontSize: 14, border: "1px solid #ddd", borderRadius: 4 }} id={`nc_${q.key}`} />
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button onClick={() => { const c = (document.getElementById(`nc_${q.key}`) as HTMLTextAreaElement)?.value || ""; api.put(`/questions/${q.key}`, { user_note: c }); }}>💾 保存</button>
            <button onClick={() => { const t = (document.getElementById(`nt_${q.key}`) as HTMLInputElement)?.value || ""; const c = (document.getElementById(`nc_${q.key}`) as HTMLTextAreaElement)?.value || ""; api.put(`/questions/${q.key}`, { user_note: c }); if (c) api.post("/notes", { title: t, content: `来源：${q.source}\n\n${c}` }); }}>📤 同步至笔记库</button>
          </div>
        </div>
      )}
    </div>
  );
}
