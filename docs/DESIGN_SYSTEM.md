# Student Competition Intelligence Design System

本设计系统用于“大学生竞赛决策与情报平台”。目标是让大量竞赛、学校政策、时间节点和推荐依据保持高信息密度，同时具备可信、清晰、轻量、年轻的产品气质。

## Brand

- 产品定位：大学生竞赛决策与情报平台，不是普通竞赛列表，也不是营销展示页。
- 核心表达：首页保留“不是所有比赛，都值得你参加。”作为品牌主张。
- 视觉基调：资料库、决策工具、可追溯情报平台。
- 设计原则：结构化信息优先，来源与依据必须显性展示，交互反馈克制。

## Colors

- Page Background: `#FFFFFF`
- Secondary Background: `#F7F8FA`
- Soft Surface: `#FAFAF9`
- Primary Ink: `#181D26`
- Secondary Text: `#5F6672`
- Muted Text: `#8A9099`
- Hairline: `#E5E7EB`
- Primary Brand: `#315EF5`
- Success / Verified: soft emerald, used for official verification and recognized policies.
- Warning / Deadline: soft orange, used for upcoming deadlines and items requiring attention.
- Purple: used sparingly for result announcements or non-primary status.

Blue is reserved for CTA, links, selected state, focused inputs, and key data. Avoid large saturated blue areas.

## Typography

- Font stack: Inter, system UI, `Segoe UI`, sans-serif.
- Hero title: 40-48px, semibold, tight but readable line height.
- Page title: 30-36px, semibold.
- Section title: 20-24px, semibold.
- Card title: 16-20px, semibold.
- Body text: 14-16px, regular, 24-28px line height.
- Labels: 12px, semibold, muted, uppercase allowed, no negative letter spacing.

## Spacing

Use the 4px base scale:

- `4px`: dense icon/text gap
- `8px`: badge and compact field gap
- `12px`: grouped metadata gap
- `16px`: card padding on dense surfaces
- `24px`: default panel padding and section gaps
- `32px`: page block gap
- `48px`: large section rhythm
- `64px`: hero and major section vertical spacing

## Radius

- Small controls and badges: `8px`
- Cards, panels, forms: `10px`
- Large grouped surfaces: `12px`
- Avoid 20px+ rounded corners unless a future design system explicitly needs it.

## Shadow

- Default panel shadow: very light, used to separate important cards from white background.
- Hover shadow: slightly stronger with `translateY(-1px)`.
- Avoid glow, neon, heavy drop shadows, glassmorphism, and decorative blur.

## Buttons

- Primary: brand blue background, white text, used for main actions such as “帮我找比赛” and “生成推荐”.
- Secondary: white background, hairline border, ink text, used for navigation and lower-priority actions.
- Minimum touch height: `44px`.
- States: hover color/border change, active `translateY(1px)`, visible focus ring.
- Icon + text is preferred for clear commands.

## Cards

- Competition cards are the primary product component and must show structured facts: status, level, name, description, direction, organizer, team type, grade, deadline, remaining time, tags, and explainable recommendation placeholder.
- Feature rows should feel editorial, not like repeated KPI cards.
- Stats use soft surfaces and numeric emphasis, avoiding heavy dashboard treatment.
- Policy and recognition cards must include verification and source affordances.

## Badge

- Badges are compact metadata, not decoration.
- Use badges for level, source type, verified status, demo data, policy type, and result count.
- Keep contrast readable but soft. Avoid saturated backgrounds.

## Tags

- Tags use soft category colors:
  - Computer / AI / AIGC / Big Data: soft blue
  - Math Modeling: soft purple
  - Innovation / Entrepreneurship / Marketing: soft orange
  - News / Video: soft pink
  - Design: soft yellow
  - Sports / Esports: soft green
  - Finance / Business: soft cyan
  - Research / Engineering: soft gray-blue
- Never tint the entire competition card by category.

## Competition Status

- 报名中: soft green
- 即将开始: soft blue
- 即将截止: soft orange
- 已截止: soft gray
- 结果公布: soft purple
- Unknown status: soft gray with cautious wording.

Status badges should include a small Lucide icon when space allows.

## Layout

- Global layout uses a sticky white header with hairline border.
- Main content width is constrained by `container-page`.
- Discovery and policy pages use a left filter/sidebar on desktop and single-column flow on mobile.
- Detail pages use main content plus a right or left facts/sidebar column.
- Avoid nested cards and oversized landing-page blocks.

## Responsive

- Target mobile widths: 375px, 390px, 430px.
- Mobile navigation collapses into a menu.
- Competition cards are single-column on mobile.
- Filters stack above results on mobile; future drawer behavior can be added without changing API.
- CTA and input touch targets must be at least `44px`.
- Text must wrap naturally without horizontal overflow or clipping.

## Motion

- Transition duration: 150ms-220ms.
- Hover: border emphasis, subtle color change, optional `translateY(-1px)`.
- Active: small press feedback.
- Focus: visible blue focus ring.
- Avoid scale jumps, complex animation, particles, glow, or background motion.
