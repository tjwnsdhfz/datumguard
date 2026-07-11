# Cost Guard and 10k DAU Model

2026-07-12 기준의 계획 문서다. **이 변경은 유료 플랜 업그레이드, 결제수단 등록, autoscaling, 외부 모니터 구매를 실행하지 않는다.** Vercel의 실제 billing plan과 Render workspace plan은 dashboard에서 재확인해야 하며, repository가 확정하는 것은 Render service `plan: free`뿐이다.

## 모델 가정

- 10,000 DAU, 30일, 1 session/DAU/day, 1~3 verification run/DAU/day.
- production root의 측정 초기 전송은 HTML+15 asset 약 388KB(폰트 제외).
- production v0.1 API 3개 sample은 18~26KB/응답, warmed latency 0.49~0.87초였다.
- 50k monthly unique browser이면 약 1.05M Vercel request와 27GiB/month; browser가 매일 새로우면 약 4.8M request와 108GiB/month다.
- API egress는 v0.1 sample 기준 약 6~18GiB/month. v0.2 STEP/upload는 live 측정 전이므로 이 수치에 포함하지 않는다.

## 공식 가격·한도

| 항목 | 현재 공개 한도 | 10k DAU 판단 |
|---|---|---|
| Vercel Hobby | $0, 1M Edge Requests, 100GB Fast Data Transfer, runtime log 1시간, personal/non-commercial | 50k MAU 가정에서도 request cap 경계; 상용/10k 출시에 부적합 |
| Vercel Pro | developer seat $20/month, $20 usage credit, 10M requests, 1TB transfer | 현재 web 모델은 포함량 안 |
| Render Free compute | $0, 0.1 CPU, 512MB; 15분 idle 뒤 spin-down, 재기동 약 1분, ephemeral FS, 수평확장/디스크 불가 | 공식 문서도 production 비권장; CAD subprocess/48MB request에 부적합 |
| Render Standard compute | $25/month, 1 CPU, 2GB | 최소 load-test 후보; HA/autoscale 보장 아님 |
| Render Pro workspace | $25/month flat, 25GB bandwidth 후 $0.15/GB, autoscaling | metrics/autoscaling이 필요하면 별도 compute와 함께 필요 |
| GitHub Actions | public repository standard runner 무료 | 현재 CI runner 비용 $0, artifact/cache 한도는 계속 관찰 |
| Sentry | Developer $0(5k errors), Team $26/month annual(50k errors) | solo beta는 free 후보, 10k DAU release는 실제 error volume으로 선택 |
| UptimeRobot | Free 50 monitors, 5-minute checks, commercial use 허용 | web/API 기본 외부 감시는 $0부터 가능 |

공식 근거: [Vercel pricing](https://vercel.com/pricing), [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Render pricing](https://render.com/pricing), [Render Free](https://render.com/docs/free), [Render workspace migration](https://render.com/docs/new-workspace-plans), [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Sentry pricing](https://sentry.io/pricing/), [UptimeRobot Free](https://help.uptimerobot.com/en/articles/11604710-who-should-use-uptimerobot-s-free-plan).

2026-07-12 Production canary에서 Render Free의 architecture는 통과했지만 OpenCascade Solid은 약 40초 뒤 HTTP 502를 반환했다. OOM 또는 worker restart는 의심되지만 직접 확인되지 않았다. 따라서 Free 배포는 Solid을 광고하지 않으며, Render Standard 이상 격리 staging에서 같은 canary와 RSS 측정을 통과하기 전 활성화하지 않는다.

## 승인 전 제안액

| 단계 | 월 고정비(USD) | 한계 |
|---|---:|---|
| 현재 portfolio | $0 가능 | cold start, 0.1 CPU/512MB, no production claim |
| Lean beta | 약 $45 = Vercel Pro 20 + Render Standard 25 | single backend, autoscaling/HA 없음; egress 별도 |
| 10k minimum HA 후보 | 약 $95 = Vercel Pro 20 + Render Pro workspace 25 + Standard 2개 50 | load test 뒤 instance/worker 조정; 계약 SLA 아님 |
| 위 + Sentry Team | 약 $121 | error quota 초과와 추가 telemetry 별도 |

Render Enterprise와 Vercel Enterprise만 명시적 uptime SLA를 제공하므로 계약 SLA가 필요하면 self-serve 계산이 아니라 견적이 필요하다.

## Guardrail

- Billing owner를 한 명 지정하고 50/75/90/100%에서 email+webhook 알림을 설정한다.
- 75%: 배포·bandwidth·error event 증가 원인 확인. 90%: 비필수 capture/load job 중단. 100%: 자동 pause 여부를 사람이 사전 승인한다.
- Render: outbound GB, CPU/RSS, instance-hours, pipeline minutes. Vercel: Edge Requests, Fast Data Transfer, build, WAF. Error tracker: events/log GB/replay sample을 각각 감시한다.
- load probe는 production에서 절대 실행하지 않으며, load-test 비용도 staging budget에 포함한다.
- 플랜 변경은 estimate, rollback 영향, 승인자, 적용 시각을 issue에 남긴 뒤 수행한다.
