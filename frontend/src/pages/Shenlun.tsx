import { useEffect, useState } from "react";
import { Card, Tabs, Select, Input, Button, message, Collapse, Tag, Space } from "antd";
import api from "../api/client";

function stripHtml(html: string) {
  return html?.replace(/<[^>]+>/g, "") || "";
}

export default function Shenlun() {
  const [exams, setExams] = useState<any[]>([]);
  const [examId, setExamId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [materials, setMaterials] = useState<any[]>([]);
  const [fetchKey, setFetchKey] = useState("");
  const [fetchPid, setFetchPid] = useState("");
  const [fetchCid, setFetchCid] = useState("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [evalResult, setEvalResult] = useState<any>(null);
  const [phrases, setPhrases] = useState<any[]>([]);
  const [phraseText, setPhraseText] = useState("");
  const [phraseTag, setPhraseTag] = useState("");
  const [phraseCat, setPhraseCat] = useState("金句");

  useEffect(() => { api.get("/shenlun/exams").then((r) => setExams(r.data)); }, []);

  const loadExam = (id: number) => {
    setExamId(id);
    api.get(`/shenlun/exams/${id}`).then((r) => {
      setQuestions(r.data.questions);
      setMaterials(r.data.materials);
    });
  };

  const doFetch = async () => {
    const r = await api.post("/shenlun/fetch", { exam_input: fetchKey, paper_id: fetchPid, check_id: fetchCid });
    if (r.data.success) { message.success(r.data.exam_name); api.get("/shenlun/exams").then((r) => setExams(r.data)); }
    else message.error(r.data.error);
  };

  const saveAnswer = async (qid: number) => {
    await api.post("/shenlun/answers", { question_id: qid, answer_text: answers[qid] || "" });
    message.success("已保存");
  };

  const evaluate = async (q: any) => {
    const matText = materials.filter((m: any) => (q._material_idxs || []).includes(m.fenbi_id)).map((m: any) => stripHtml(m.content).slice(0, 500)).join("\n");
    const r = await api.post("/shenlun/evaluate", { question_id: q.id, question: stripHtml(q.content), answer: answers[q.id] || "", materials: matText, question_type: q.question_type, score: String(q.score), word_limit: q.word_limit });
    setEvalResult(r.data);
  };

  const savePhrase = async () => {
    if (!phraseText) return;
    await api.post("/shenlun/phrases", { content: phraseText, tag: phraseTag, category: phraseCat });
    message.success("已收藏");
    api.get("/shenlun/phrases").then((r) => setPhrases(r.data));
  };

  return (
    <div>
      <h2>📝 申论</h2>
      <Tabs items={[
        {
          key: "practice", label: "真题练习",
          children: <div>
            <Collapse items={[{
              key: "fetch", label: "📥 抓取真题",
              children: <Space>
                <Input placeholder="Exam Key" value={fetchKey} onChange={(e) => setFetchKey(e.target.value)} />
                <Input placeholder="paperId" value={fetchPid} onChange={(e) => setFetchPid(e.target.value)} />
                <Input placeholder="checkId" value={fetchCid} onChange={(e) => setFetchCid(e.target.value)} />
                <Button onClick={doFetch}>抓取</Button>
              </Space>
            }]} />
            <Select placeholder="选择试卷" style={{ width: "100%", marginTop: 12 }}
              value={examId} onChange={loadExam}
              options={exams.map((e: any) => ({ value: e.id, label: `${e.name?.slice(0, 30)} (${e.date})` }))} />
            {questions.map((q: any) => {
              const qMats = materials.filter((m: any) => (q._material_idxs || []).includes(m.fenbi_id));
              return (
                <Card key={q.id} style={{ marginTop: 12 }} title={`${q.question_number} - ${q.question_type} (${q.score}分, ${q.word_limit}字)`}>
                  {qMats.map((m: any) => <div key={m.id}><div dangerouslySetInnerHTML={{ __html: m.content?.slice(0, 3000) }} style={{ background: "#f9f9f9", padding: 12, borderRadius: 4, marginBottom: 8, maxHeight: 200, overflow: "auto" }} /></div>)}
                  <div dangerouslySetInnerHTML={{ __html: q.content }} style={{ marginTop: 8 }} />
                  <Input.TextArea rows={6} placeholder="在此作答..." value={answers[q.id] || ""}
                    onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} style={{ marginTop: 8 }} />
                  <Space style={{ marginTop: 8 }}>
                    <Button onClick={() => saveAnswer(q.id)}>💾 保存</Button>
                    <Button type="primary" onClick={() => evaluate(q)}>🤖 AI 批改</Button>
                  </Space>
                  {evalResult && <Card size="small" style={{ marginTop: 8 }}>
                    <p><Tag color="blue">总评 {evalResult.total_score}/100</Tag></p>
                    <p>内容 {evalResult.content_score} | 结构 {evalResult.structure_score} | 语言 {evalResult.language_score}</p>
                    <p>点评：{evalResult.comments}</p>
                    <p>改进：{evalResult.improvement}</p>
                  </Card>}
                </Card>
              );
            })}
          </div>
        },
        {
          key: "phrases", label: "素材库",
          children: <div>
            <Space style={{ marginBottom: 8 }}>
              <Input placeholder="内容" value={phraseText} onChange={(e) => setPhraseText(e.target.value)} />
              <Input placeholder="标签" value={phraseTag} onChange={(e) => setPhraseTag(e.target.value)} />
              <Select value={phraseCat} onChange={setPhraseCat} options={["金句", "模板", "规范表述", "领导人讲话", "名言"].map((s) => ({ value: s, label: s }))} />
              <Button onClick={savePhrase}>收藏</Button>
            </Space>
            {phrases.map((p: any) => (
              <Card key={p.id} size="small"><Tag>{p.category}</Tag> {p.tag && <Tag color="blue">{p.tag}</Tag>} {p.content}</Card>
            ))}
          </div>
        },
      ]} />
    </div>
  );
}
