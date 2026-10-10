"use client";

import { useState } from "react";
import type { University, UniversityDetail } from "@/lib/types";

export function SchoolSelector({ universities, universityId = "", collegeId = "", selectedUniversity }: {
  universities: University[];
  universityId?: string;
  collegeId?: string;
  selectedUniversity?: UniversityDetail | null;
}) {
  const [school, setSchool] = useState(universityId);
  const [college, setCollege] = useState(collegeId);
  const colleges = String(selectedUniversity?.id) === school ? selectedUniversity?.colleges ?? [] : [];
  return <>
    <label className="grid gap-2">
      <span className="label">我的学校</span>
      <select className="field" name="university_id" value={school} onChange={(event) => { setSchool(event.target.value); setCollege(""); }}>
        <option value="">全部学校</option>
        {universities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    <label className="grid gap-2">
      <span className="label">学院</span>
      <select className="field" name="college_id" value={college} onChange={(event) => setCollege(event.target.value)} disabled={!colleges.length}>
        <option value="">全校范围</option>
        {colleges.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      {school && String(selectedUniversity?.id) !== school ? <span className="text-xs text-muted">应用学校后可继续选择学院</span> : null}
    </label>
  </>;
}
