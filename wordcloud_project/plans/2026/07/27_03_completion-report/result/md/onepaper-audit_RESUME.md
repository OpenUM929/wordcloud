onepaper 02-page-budget 감사 체크포인트 (1/3 지면예산 산술검산) 시작 260805
[FACT] 정본확정 01-spec 1-1: A4 210x297, 여백 프리셋 20/30/40mm 상하좌우 동일, 기본 여백20 -> 인쇄폭 170mm / 인쇄높이 257mm. 문서 2-1 기준상수 일치 (이상없음)
[FACT] 정본확정 01-spec 1-2: 본문 12pt 행간 1.9, h1 20pt, h2 15pt, h3 13pt, h4 11.5pt, 표 10.5pt 고정폭(fixed), 이미지 폭100% 자동맞춤. 01-spec 1-4: one-paper pageMode single + 첫 인용문 헤드라인밴드 가운데 14pt Bold. 문서 2-1 3행 전부 일치 (이상없음)
[FACT] 04-engine 4-3 원문 실재 확인: 'report 테마 본문 12pt·행간 1.9 -> 페이지당 약 32줄(257mm ÷ ~8mm)'. 문서 13행의 인용 주장 참
[FACT] 재계산 13행: 12x1.9=22.8pt, x0.352778=8.0433mm, 257/8.0433=31.95줄. 문서값 8.04mm/31.95줄 일치 (이상없음)
[UNCERTAIN] 01-spec 1-5는 print.css 통합빌드 경로 기준 h1 18pt/h3 12pt/본문 10.5pt 로 1-2와 다른 값 제시. 02-page-budget 은 어느 렌더경로 기준인지 미명시 (27-document-output-standard 2절 '렌더경로 작성전 확정' 위반 소지). one-paper reportTheme 는 편집기 경로이므로 1-2 채택은 타당 추정
[FACT] 03-page-composition 3-5: '테마 표는 table-layout fixed 라 폭이 균등 분배' 확인 -> 2-3 의 170/n 열폭 산정 근거 성립 (이상없음)
[FACT] 2-2 산술 셀단위 재가산: 프리셋A 20+12+23+30+41+23+(9+8)+23+8=197mm 일치, 프리셋B 20+12+23+30+23+23+9+23+8=171mm 일치. 249-197=52, 249-171=78 일치. 각 섹션 내부합(h3 9 + 표행수x7)도 전부 일치 -> 문서 내부 산술은 무결
[FACT] 2-2 비중 분모: 52/257=20.23%(20.2), 78/257=30.35%(30.4) -> 분모는 249 아닌 257. 두 값 모두 257로 일관되나 문서에 분모 미명시. 249 기준이면 20.9%/31.3%
[FACT] 종횡비 170/52=3.269->3.3 올림, 170/78=2.179->2.18->2.2 올림. 최소요구값 올림은 보수측 (이상없음)
[FACT] 2-3 전 항목 재계산 일치: 12pt=4.2336, 10.5pt=3.7044, 14pt=4.939, 20pt=7.056 / 170/4.23=40.19 / 164/4.23=38.77(문서 38.7 절사표기) / (85-4)/3.7=21.89 / (56.7-4)/3.7=14.24 / (42.5-4)/3.7=10.405 / 170/4.94=34.41 / 170/7.06=24.08. 42.5=170/4, 56.7=170/3, 85=170/2 확인
[FACT] 2-4 전 항목 재계산 일치: 13x170/1920=1.151mm(3.26pt), /1280=1.727(4.89pt), /1100=2.009(5.69pt), /900=2.456(6.96pt). W<=85h 는 170/2.0=85 로 도출 정합, 13x85=1105->1100 내림 보수. 16:9 -> 170x9/16=95.625->96mm, 78mm 초과 성립
[FACT] 원자료 추적: 01-spec 7행이 '보고서 양식은 src/app/report-theme.css 가 구현한다'고 지정 -> 실제 구현본 D:/dev/md_editor/md_editor/src/app/report-theme.css (400행) 대조함
[FACT] CSS 326행: report-theme--one-paper 컨테이너 font-size 11.5pt 로 베이스 12pt 를 덮어씀(6행: 클래스가 report-theme 와 report-theme--one-paper 동시 부여, 동일 특정도 후순위 승). 즉 one-paper 본문은 12pt 아님 -> 8.04mm/40자 근거가 테마와 불일치(단 방향은 보수측: 실제 7.71mm/41.9자)
[FACT] CSS 실측 박스: h1 20pt/lh1.25 + padding 8pt x2 + border 0.7+1.4 = 43.1pt=15.21mm, margin-bottom 14pt -> 20.15mm. 문서 20mm 와 일치(이상없음)
[FACT] CSS 332-343행 밴드: blockquote:first-of-type font 14pt, line-height 는 베이스 blockquote 1.5 상속 -> 21pt + padding 11pt x2 + border 1.6pt x2 = 46.2pt = 16.30mm (margin 6/14 별도). 문서 12mm 는 박스만으로도 4.3mm 부족
[FACT] CSS 134-151행 표: line-height 1.4(1.9 아님), td/th padding 4pt 5pt, border 0.6pt, table margin 5pt 0 12pt. 일반 표 1행 = 10.5x1.4=14.7 + 8 + 0.6 = 23.3pt = 8.22mm. 문서 7mm 는 행당 1.22mm 과소, 표 상하 margin 17pt(6.0mm)는 아예 미계상
[FACT] CSS 361-377행 one-paper 첫 표 override: th 9.5pt, 첫 tbody 행 td 15pt + padding 7/4. 템플릿 1번 사업개요 4열표가 첫 표에 해당 -> 헤더행 21.9pt(7.73mm) + 값행 32.6pt(11.50mm) = 19.2mm, 문서 14mm 대비 5.2mm 과소
[FACT] CSS 64-69행 h3: 13pt lh 1.4 = 18.2pt = 6.42mm 본체, margin 14pt/5pt. 문서 9mm 는 본체보다 크나 상하 margin(6.7mm) 미계상
[INFERENCE] CSS 실측값으로 프리셋 전체 재적산(표준 박스모델 + 인접 margin collapse 적용): 프리셋A 텍스트 251.1mm (문서 197mm, 54mm 과소) -> 이미지 상한 257-251.1=5.9mm (문서 52mm), 안전여유 8mm 적용시 -2.1mm 로 배치 불가
[INFERENCE] 프리셋B 텍스트 220.7mm (문서 171mm, 50mm 과소) -> 이미지 상한 36.3mm (문서 78mm), 비중 14.1%(문서 30.4%), 필요 종횡비 4.7:1(문서 2.2:1). 안전여유 8mm 적용시 28.3mm/6.0:1
[FACT] 과소계상 원인 3종: (1) 블록간 margin 전량 미계상(h3 14/5pt, 표 5/12pt, 밴드 6/14pt, 이미지 6/12pt) (2) 표 셀 세로 패딩 4pt x2 + border 미계상 (3) 밴드/표에 행간 1.9 가정했으나 실제 CSS 는 밴드 1.5 표 1.4, 대신 padding 이 더 큼
[JUDGMENT-DRAFT] 치명: 안전여유 8mm(3%)가 흡수한다는 주장 불성립. 실측 편차 A +54mm(27%) B +50mm(29%) 로 여유의 6배 이상
[FACT] 결정적 대조: 문서값은 CSS 박스(폰트x행간+padding+border) 합계와 거의 정확히 일치 -> A 198.1mm(문서 197), B 171.9mm(문서 171). 누락분은 전액 블록간 마진 A 153pt=54.0mm / B 141pt=49.7mm. 즉 문서 모델은 마진 0 가정
[FACT] 04-template-body 4-1 확인: 1번 사업개요 표가 문서 첫 표 = one-paper KPI 오버라이드 대상. 4-2 슬롯 상한 각 10자는 값행 15pt 기준 (42.5-4)/5.29=7.3자 -> 10자면 줄바꿈 발생, 행높이 2배
[FACT] 전파 확인: 78mm/30.4% 는 03-writing-rules 11행 OP-1, 52mm 는 04-template-body 57행, 1100px/2.2:1 은 04-template-body 71행 및 06-checklist 11행에 동일값으로 재기재. 값 불일치는 없음(전부 02 를 승계) -> 02 가 틀리면 4개 문서 동시 오류
[FACT] 민감도 h1 20mm 50%: A텍스트 187/207 -> 이미지 62/42mm(24.1%/16.3%), B 161/181 -> 88/68mm(34.2%/26.5%)
[FACT] 민감도 밴드 12mm 50%: A 191/203 -> 58/46mm(22.6%/17.9%), B 165/177 -> 84/72mm(32.7%/28.0%). B 는 상향시 30% 원칙 붕괴
[FACT] 민감도 셀패딩 4mm 50%(2/6mm): 4열 10.9/9.86 -> 10자/9자, 3열 14.8/13.7 -> 14/13자, 2열 22.4/21.4 -> 22/21자. 최대 1자 변동, 둔감
[FACT] 민감도 판독하한 2.0mm 50%(1.0/3.0mm): W<=170h/56.7h -> h=13 에서 2210px/737px. 1.0mm 이면 전체화면 1920px 이 합격으로 뒤집힘. 단 지면축(96mm)은 독립 성립하므로 결론 유지
[JUDGMENT] 1/3 범위 판정 = 재작성 필요 (2-1 요소높이표/2-2 예산표. 2-3 글자수/2-4 캡처규격은 산술 무결)
===== 2차 재감사 260805 (범위: R-1~R-6) =====
[FACT] R-2 핵심전제 확정: globals.css 289-299 셀렉터 .print-pages :is(th,td) 안 297행 font-size 0.95em / 298행 line-height 1.35 실재. report-theme.css 142-151 의 td 규칙은 border/padding/word-break/vertical-align 4개만 선언(폰트크기·행간 미선언) -> 상속 아닌 globals 선언이 그대로 적용. 특정도 report-theme (0,3,1) > globals (0,1,1) 이나 겹치는 속성이 없어 무충돌
[FACT] em 기준 검증: td 부모는 tr>tbody>table, tr/tbody 는 font-size 미선언 -> table 의 10.5pt(report-theme 139행) 상속. 따라서 0.95em = 9.975pt 성립. 작성자 전제 참. 1차 감사의 10.5pt 가정(8.22mm)은 오류였음 -> C-2 관련 1차 지적 일부 철회
[FACT] globals 435행 print 미디어 .print-pages :is(table,th,td) 는 border-color 만 지정 -> 폰트 영향 없음. globals 144-149 h1-h4 margin/line-height 는 report-theme (0,3,1) 이 전부 덮음. 확인 완료
[FACT] 2-2 요소별 높이 전량 재계산 일치: h1 15.2047 / 메타 7.0379 / 밴드 16.2983 / h3 6.4206 / p 7.7082 / 일반표1행 7.7845 / 2행 15.7806 / 첫표헤더 7.5583 / 첫표값행 11.2360 / 첫표2행 19.0059. 마진값도 CSS 원문 일치(h1 mb14, meta -8/12, band 6/14, h3 14/5, table 5/12, img 6/12, blockquote 4/8, hr 12/12)
[FACT] 2-2 유일 편차: 일반표 3행 문서 23.56 vs 정밀 23.5651 (반올림하면 23.57). 0.01mm, 무해
[FACT] 2-3 프리셋 총계 독립 재적산(04-template-body 4-1 블록열 + collapse 규칙): V = 153.5898mm (문서 153.6), T = 197.2871mm (문서 197.3). 차 43.697 (문서 43.7). 전부 일치
[FACT] 이미지 상한: 249-153.59=95.41 -> 95mm 내림채택, 249-197.29=51.71 -> 51mm 내림채택 (보수측). 비중 51/257=19.84->19.8, 95/257=36.96->37.0, 77/257=29.96->30.0. 종횡비 170/51=3.33->3.4, 170/95=1.79->1.8, 170/77=2.21->2.3 전부 일치
[FACT] R-3 성립: tiptap-editor.tsx 354-355 const html = editor.getHTML(); printEl.innerHTML = html -> 인쇄면은 getHTML 직렬화 확정. 470행 div className print-pages prose max-w-none
[FACT] R-3 tableWrapper: node_modules/@tiptap/extension-table/dist/index.js 482행 renderWrapper 기본 false, 515행 renderWrapper 일 때만 div.tableWrapper 삽입. tiptap-editor.tsx 159행 Table.configure({resizable:true}) 로 renderWrapper 미지정 -> getHTML 에 래퍼 없음. 230행 TableView(에디터 NodeView)만 tableWrapper 클래스 부여 -> 편집화면 전용 맞음. 작성자 주장 참, 안전여유 8mm 전제 붕괴 없음
[INFERENCE] R-3 편집화면 20mm 주장 재계산: 표 4개가 BFC 래퍼에 갇히면 T 에서 약 +56pt=19.8mm, V 에서 약 +26pt=9.2mm. 최대 20mm 표현 타당
[FACT] R-2 2-4 감액 전량 재검산 일치(pt 정밀): -28.9(81.93pt) / -20.5(58.2pt) / -8.9(25.2pt) / -8.2(23.2pt) / -9.2(26.2pt) / -8.4(23.95pt) / -7.8(22.07pt) / 캡션 +11.9(33.85pt, 뒤가 h3) 및 +9.5(26.85pt, 뒤가 표). 초안 +7.7 을 +11.9 로 고친 것이 옳음. T 기준 문서이므로 헤드라인 +11.9 채택 타당
[FACT] R-2 2-5 안전여유: 1.8=각주 p mb 5pt(1.7639) / 4.8=9.975x1.35=13.466pt(4.7507) 근거 CSS 일치. 0.6/0.5 는 근거 없는 가정이나 가정임을 명시. 합 7.7 -> 8 산술 일치
[FACT] R-2 7-1 글자수 전 행 재검산 일치: h1 23.4 / 메타 45.9 / 밴드 33.9 / h3 36.6 / 본문 41.9 / li 40.2 / 첫표헤더 11.6 / 첫표값행 7.459(문서 7.5, 채택 7자) / 3열 10.1 / 2열 15.5 / 일반표 23.1,15.0,11.0. 패딩 출처 CSS 일치(th,td 4pt 5pt / 첫표값행 7pt 4pt 4pt / h1 8pt 6pt / 밴드 11pt 4pt)
[FACT] R-2 7-2 캡처 전 행 일치: 1.151/1.727/2.009/2.456/3.437mm, 85h 도출, 170mm=642.52 CSS px -> 643 올림 보수, 16:9 = 95.625 -> 95.6mm
[FACT] R-2 마진 collapse 총계: T gaps 126pt = 44.45mm (문서 44.5), V gaps 97pt = 34.22mm (문서 34.2) 일치
[FACT] 신규 발견 근거1: node_modules/@tiptap/extension-table/dist/index.js 43행 tableCell content block+ , 91행 tableHeader content block+ , 528/543행 parseMarkdown 이 셀마다 {type:paragraph} 노드 생성 -> getHTML 직렬화 결과는 td 안에 p 가 들어간다
[FACT] 신규 발견 근거2: report-theme.css 86-88행 p { margin: 0 0 5pt } 셀렉터 특정도 (0,3,1) 로 td 내부 p 에도 적용. globals/report-theme/@tailwindcss-typography styles.js 전수 grep 결과 td p 또는 blockquote p 마진을 0 으로 되돌리는 규칙 없음(typography 의 > :last-child 는 .prose 직계만, 게다가 (0,1,0) 로 짐)
[FACT] 신규 발견 근거3: td padding 4pt(하) 및 blockquote padding 11pt/4pt(하) 가 0 이 아니므로 자식 p 하단 마진이 collapse-through 하지 못함. table-cell 은 BFC 라 마지막 자식 하단 마진이 콘텐츠 높이에 포함
[INFERENCE] 치명 신규: 문서 2-1 행 높이 공식이 셀 내부 p 하단 마진 5pt 를 누락. 실제 일반표 1행 27.066pt=9.55mm(문서 7.78) / 첫표 2행 22.53mm(문서 19.01) / 밴드 18.06mm(문서 16.30)
[INFERENCE] 재적산: T 텍스트 214.93mm(문서 197.3, +17.6) -> 이미지 34mm(13.3%, 5.0:1). V 텍스트 169.46mm(문서 153.6, +15.9) -> 이미지 79mm(30.9%, 2.2:1). 편차가 안전여유 8mm 의 2배 -> 1차 사고와 같은 계열(규모만 1/3)
[INFERENCE] 결론 반전 1건: V 이미지 상한 79mm 이면 16:9 95.6mm 를 지면 축이 16.6mm 차로 걸러낸다. 07-2 55/57행, 03 OP-6 16행, 03 X-4 45행, 08 56행의 "가독성 축이 유일한 게이트" 가 틀림. 단 안전 방향(더 보수)
[UNCERTAIN] 위 3건은 렌더 실측 미수행. 검증법: 인쇄 미리보기 DevTools 에서 일반 표 1행 tr 높이 측정. 예측 36.1px(9.55mm) vs 문서모델 29.4px(7.78mm). 이 한 번의 측정으로 결론남
[FACT] R-4 폐기값 전수 grep(171/20.2/30.4/2.2:1/프리셋A,B/12pt/8.04/7mm/12mm/9mm/30자/35자/21-14-10자/197/52/78/두 축 모두 실격): 전량 08-revision-log 구 값 열에만 존재하고 폐기 또는 신 값이 병기됨 -> 정상. 잔존 위반 1건 = 05-evidence-ledger 32행 "인쇄면 라벨(10자)" (현행 첫 표 헤더 상한은 11자, 대조표 아닌 본문 서술)
[FACT] R-5 문서간 대조 이상 없음: 51/77/95mm, 19.8/30.0/37.0%%, 3.4/2.3/1.8:1, 7자/44자/22자/32자/11자/14자/40자, 643~1,100px, 8mm, 20mm, 249/257 전부 9문서에서 값 일치. 나침반 하위문서 8행이 실재 파일 8개와 1:1 대응
[FACT] R-6 정직고지 실재 확인: 실측 미검증 = 나침반 48행 / 02 5행 / 06 45행 / 07 4행 / 08 67행. T 30퍼 불가 = 02 63행 / 03 11행 / 04 78행 / 06 13행 (사용자 동선 4곳). 구 서술 두 축 모두 실격 은 08 56행 대조표에만
[JUDGMENT] 2차 재감사 판정 = 수정 필요. C-1~C-5 및 G-1~G-5 전 10건 해소 확인. 단 셀 내부 p 하단 마진 누락으로 2-2/2-3/2-4 및 07-2 결론 1건 재산 필요
