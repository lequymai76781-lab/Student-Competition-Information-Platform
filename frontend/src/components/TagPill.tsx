import { getTagTone } from "@/lib/taxonomy";

type TagPillProps = {
  label: string;
};

export function TagPill({ label }: TagPillProps) {
  return <span className={`tag-soft ${getTagTone(label)}`}>{label}</span>;
}

