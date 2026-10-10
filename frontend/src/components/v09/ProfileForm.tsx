"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getAllUniversities } from "@/lib/api";
import { interestOptions, universityColleges, updateProfile, type V09Profile } from "@/lib/v09-api";

type UniversityOption = { id: number; name: string; short_name?: string | null };
type CollegeOption = { id: number; name: string };

const grades = ["大一", "大二", "大三", "大四", "研究生一年级", "研究生二年级", "研究生三年级"];

export function ProfileForm({
  initial,
  title,
  submitLabel = "保存并继续",
  redirectTo = "/my-competitions",
}: {
  initial?: V09Profile | null;
  title?: string;
  submitLabel?: string;
  redirectTo?: string;
}) {
  const router = useRouter();
  const [universities, setUniversities] = useState<UniversityOption[]>([]);
  const [colleges, setColleges] = useState<CollegeOption[]>([]);
  const [interestOptionsList, setInterestOptionsList] = useState<{ label: string; tags: string[] }[]>([]);
  const [universityName, setUniversityName] = useState(initial?.university_name ?? "");
  const [collegeName] = useState(initial?.college_name ?? "");
  const [collegeFreeText, setCollegeFreeText] = useState("");
  const [majorName, setMajorName] = useState(initial?.major_name ?? "");
  const [grade, setGrade] = useState(initial?.grade ?? "");
  const [interests, setInterests] = useState<string[]>(initial?.interest_tags ?? []);
  const [teamType, setTeamType] = useState(initial?.preferred_team_type ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getAllUniversities().then(setUniversities).catch(() => setError("学校列表加载失败，请刷新重试。"));
    interestOptions().then(setInterestOptionsList).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!initial?.university_id) return;
    universityColleges(initial.university_id).then(setColleges).catch(() => undefined);
  }, [initial?.university_id]);

  const matchedUniversity = useMemo(
    () => universities.find((item) => item.name === universityName),
    [universities, universityName],
  );
  const filteredColleges = useMemo(
    () => (collegeName ? colleges.filter((item) => item.name.includes(collegeName)) : colleges),
    [colleges, collegeName],
  );
  const selectedCollege = useMemo(
    () => colleges.find((item) => item.name === (collegeFreeText || collegeName)),
    [colleges, collegeFreeText, collegeName],
  );

  async function save() {
    setBusy(true);
    setError("");
    try {
      const payload: Partial<V09Profile> = {
        university_id: matchedUniversity?.id,
        university_name: universityName.trim() || undefined,
        college_id: selectedCollege?.id,
        college_name: (selectedCollege?.name ?? collegeFreeText ?? collegeName ?? "").trim() || undefined,
        major_name: majorName.trim() || undefined,
        grade: grade || undefined,
        interest_tags: interests,
        preferred_team_type: teamType || undefined,
      };
      await updateProfile(payload);
      router.push(redirectTo);
      router.refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="panel p-6">
        {title ? <h2 className="text-xl font-semibold text-ink">{title}</h2> : null}
        <div className="mt-5 grid gap-4">
          <Field label="1. 你的学校">
            <input
              list="university-options"
              value={universityName}
              onChange={(event) => {
                setUniversityName(event.target.value);
                setColleges([]);
                const match = universities.find((item) => item.name === event.target.value);
                if (match) universityColleges(match.id).then(setColleges).catch(() => undefined);
              }}
              placeholder="输入或选择学校，如：武汉体育学院"
              className="field"
            />
            <datalist id="university-options">
              {universities.map((item) => (
                <option key={item.id} value={item.name} />
              ))}
            </datalist>
          </Field>

          <Field label="2. 你的学院">
            <input
              list="college-options"
              value={collegeFreeText || collegeName}
              onChange={(event) => setCollegeFreeText(event.target.value)}
              placeholder={filteredColleges.length ? "选择或输入学院名称" : "未收录时可手动输入，例如：新闻传播学院"}
              className="field"
            />
            <datalist id="college-options">
              {filteredColleges.map((item) => (
                <option key={item.id} value={item.name} />
              ))}
            </datalist>
            {filteredColleges.length === 0 && universityName ? (
              <p className="mt-1 text-xs text-muted">当前库中暂无该校学院目录，可手动输入标准化名称。</p>
            ) : null}
          </Field>

          <Field label="3. 你的专业">
            <input
              value={majorName}
              onChange={(event) => setMajorName(event.target.value)}
              placeholder="例如：播音主持 / 计算机科学"
              className="field"
            />
          </Field>

          <Field label="4. 当前年级">
            <select value={grade} onChange={(event) => setGrade(event.target.value)} className="field">
              <option value="">请选择</option>
              {grades.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>

          <Field label="5. 感兴趣的方向（可多选，后期可补技能）">
            <div className="flex flex-wrap gap-2">
              {interestOptionsList.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() =>
                    setInterests((current) =>
                      current.includes(option.label)
                        ? current.filter((item) => item !== option.label)
                        : [...current, option.label],
                    )
                  }
                  className={
                    interests.includes(option.label)
                      ? "tag-soft border-blue-200 bg-blue-50 text-accent"
                      : "tag-soft border-line bg-paper text-muted"
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="参赛形式偏好（可选，不影响筛选，只影响排序理由）">
            <select value={teamType} onChange={(event) => setTeamType(event.target.value)} className="field">
              <option value="">不限</option>
              <option value="个人">个人赛优先</option>
              <option value="团队">团队赛优先</option>
            </select>
          </Field>
        </div>
        <p className="mt-5 text-xs leading-5 text-muted">
          你提交的学校/学院/专业与兴趣信息仅用于本平台的个性化赛事筛选与提醒，不会公开。
        </p>
        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
        <button type="button" onClick={save} disabled={busy || !universityName.trim()} className="button-primary mt-6 w-full">
          {busy ? "保存中…" : submitLabel}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}
