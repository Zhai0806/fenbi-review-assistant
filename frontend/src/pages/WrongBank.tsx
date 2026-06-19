import { useEffect, useState, useRef } from "react";
import { Select, Button, Card, Radio, message, Progress, Slider, Switch, Space } from "antd";
import api from "../api/client";

function idxToLetter(i: string | number) {
  const m: Record<string, string> = { "0": "A", "1": "B", "2": "C", "3": "D" };
  return m[String(i)] || String(i);
}

export default function WrongBank() {
  const [pool, setPool] = useState<any[]>([]);
  const [module, setModule] = useState("全部");
  const [count, setCount] = useState(10);
  const [shuffle, setShuffle] = useState(true);
  const [questions, setQuestions] = useState<any[]>([]);
  const [idx, setIdx] = useState(0);
  const [score, setScore] = useState(0);
  const [choice, setChoice] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [startTime, setStartTime] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [confidence, setConfidence] = useState<number>(3);
  const [calibration, setCalibration] = useState<any[]>([]);
  const timer = useRef<any>(null);

  useEffect(() => {
    if (questions.length > 0 && idx < questions.length) {
      setStartTime(Date.now());
      timer.current = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000);
    }
    return () => clearInterval(timer.current);
  }, [idx, questions]);

  const fetchQuestions = () => {
    api.get("/wrong-bank", { params: { module, count, shuffle } }).then((r) => {
      setQuestions(r.data); setIdx(0); setScore(0); setSubmitted(false); setChoice(null); setStartTime(Date.now());
    });
  };

  const submit = () => {
    if (!choice) return;
    setSubmitted(true);
    const q = questions[idx];
    const correct = String(q.correct_answer);
    const isRight = String(choice) === correct;
    if (isRight) setScore((s) => s + 1);
    clearInterval(timer.current);
    // 记录校准数据
    setCalibration(prev => [...prev, { conf: confidence, correct: isRight, q: q.source }]);
    message.info(isRight ? "✅ 正确!" : `❌ 正确是 ${idxToLetter(correct)}`);
  };

  const next = () => {
    setChoice(null); setSubmitted(false);
    if (idx + 1 >= questions.length) {
      message.success(`完成! ${score}/${questions.length} (${questions.length > 0 ? (score / questions.length * 100).toFixed(0) : 0}%)`);
      if (calibration.length > 0) {
        setTimeout(() => {
          const msg = [
            highConfWrong > 0 ? `⚠️ ${highConfWrong}道你很有把握但做错了——这是最危险的盲区` : "",
            lowConfRight > 0 ? `💡 ${lowConfRight}道你没把握但做对了——说明你低估了自己` : "",
          ].filter(Boolean).join("；");
          if (msg) message.warning(msg, 10);
        }, 500);
      }
    } else {
      setIdx((i) => i + 1);
    }
  };

  const q = questions[idx];
  const done = idx >= questions.length || !q;

  // 校准统计
  const highConfWrong = calibration.filter(c => c.conf >= 4 && !c.correct).length;
  const lowConfRight = calibration.filter(c => c.conf <= 2 && c.correct).length;

  return (
    <div>
      <h2>📖 错题本</h2>
      <Space style={{ marginBottom: 16 }}>
        <Select value={module} onChange={setModule} style={{ width: 120 }}
          options={["全部", "政治理论", "常识判断", "言语理解与表达", "数量关系", "判断推理", "资料分析"].map((m) => ({ value: m, label: m }))} />
        <Slider min={5} max={30} value={count} onChange={setCount} style={{ width: 120 }} />
        <span>乱序 <Switch checked={shuffle} onChange={setShuffle} /></span>
        <Button type="primary" onClick={fetchQuestions}>开始练习</Button>
      </Space>

      {!done && (
        <Card title={`第 ${idx + 1}/${questions.length} 题 | ⏱ ${elapsed}s | ✅ ${score}/${idx}`}>
          <Progress percent={Math.round((idx / questions.length) * 100)} showInfo={false} />
          <p style={{ marginTop: 8, color: "#888" }}>{q.module} | {q.exam_name?.slice(0, 20)} | {q.source}</p>
          <div dangerouslySetInnerHTML={{ __html: q.content?.replace(/src="\/\//g, 'src="https://') }} />

          <Radio.Group value={choice} onChange={(e) => !submitted && setChoice(e.target.value)}
            style={{ display: "block", marginTop: 12 }}>
            {q.options?.map((opt: string, oi: number) => (
              <Radio key={oi} value={String(oi)} style={{ display: "block", marginBottom: 8 }}>
                {idxToLetter(oi)}. {opt}
              </Radio>
            ))}
          </Radio.Group>

          {submitted && (
            <div style={{ marginTop: 12, padding: 8, background: "#f5f5f5", borderRadius: 4 }}>
              <p>🖊 你的: {idxToLetter(q.your_answer)} | ✅ 正确: {idxToLetter(q.correct_answer)}</p>
              <p>原错因: {q.error_type || "未标注"} | 用时: {q.time_sec}s</p>
            </div>
          )}

          <Space style={{ marginTop: 16 }} direction="vertical" style={{ width: "100%" }}>
            {!submitted && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "#999" }}>你有多少把握？</span>
                {[1, 2, 3, 4, 5].map(n => (
                  <span key={n} onClick={() => setConfidence(n)} style={{
                    cursor: "pointer", padding: "2px 8px", borderRadius: 4, fontSize: 13,
                    background: confidence === n ? "#1a73e8" : "#f0f0f0",
                    color: confidence === n ? "#fff" : "#666",
                  }}>{n}</span>
                ))}
              </div>
            )}
            {!submitted ? (
              <Button type="primary" onClick={submit} disabled={!choice}>提交</Button>
            ) : (
              <Button type="primary" onClick={next}>{idx + 1 >= questions.length ? "完成" : "下一题"}</Button>
            )}
            <Button onClick={() => { if (idx + 1 < questions.length) { setIdx((i) => i + 1); setChoice(null); setSubmitted(false); } }} disabled={submitted}>跳过</Button>
          </Space>
        </Card>
      )}
    </div>
  );
}
