# 코치 캐릭터

`coach-mascot-d-base.png`는 사용자가 선택한 네 번째 시안(보라색 입체 말풍선 두 개)의 애니메이션용 베이스다. 내장 `image_gen`으로 생성·편집했으며, 투명 배경을 유지했다.

선택한 시안의 두 눈동자만 지운 이미지 위에 `app/templates/_coach_mascot.html`의 SVG 눈동자와 반사광을 겹친다. 몸체는 움직이지 않으며 눈동자만 CSS로 좌우를 살핀다. 실제 이용자나 금융기관의 이미지를 사용하지 않았다.

최종 편집 프롬프트:

> Use case: precise-object-edit. This is an animation base layer for the EXACT attached purple 3D speech-bubble mascot. Preserve this character's exact identity, body silhouette, pose, front and back speech bubbles, placement, size, smile, eye socket positions and shapes, purple colors, soft 3D clay shading, lighting and transparent canvas. Change ONLY the two pupils: remove both dark purple pupils and their tiny bright glossy glints, filling their areas seamlessly with the same creamy off-white eye surface so that both eyeballs become blank off-white ovals ready for separately animated pupils. Do NOT remove the eye whites or move the eyes. Keep their existing natural eye shading. Do not modify the mouth or add any accessories, objects or text. Do not restyle, recolor, resize or rotate the mascot. Preserve the original square canvas and margins and actual transparent background. No outline, floor, cast shadow, glow, watermark, or background. This is a technical character animation asset, not a concept variant.
