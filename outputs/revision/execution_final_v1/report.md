# Execution sensitivities trên predictions T04

| Scenario | B mean return (%) | AS mean return (%) | AS − reference (pp) | AS BUY | AS residual |
|---|---:|---:|---:|---:|---:|
| reference | -0.749513 | -0.796962 | -0.000000 | 24 | 0 |
| pending_t2 | -0.749513 | -0.796962 | -0.000000 | 24 | 0 |
| advance_on_demand | -0.749513 | -0.796962 | -0.000000 | 24 | 0 |
| advance_auto | -0.803265 | -0.839653 | -0.042691 | 24 | 0 |
| lower_cost | -0.525765 | -0.611625 | 0.185337 | 24 | 0 |
| higher_cost | -1.248588 | -1.211048 | -0.414086 | 24 | 0 |
| sell_charge_10bp | -0.805430 | -0.843310 | -0.046348 | 24 | 0 |
| no_fill_proxy | -0.659367 | -0.802857 | -0.005895 | 23 | 0 |
| delayed_proxy | -0.620770 | -0.766477 | 0.030485 | 24 | 0 |
| lot100_cap1pct | -0.601612 | -0.745248 | 0.051715 | 23 | 0 |
| combined | -1.074235 | -1.165626 | -0.368663 | 23 | 0 |
| all_entries_missed | 0.000000 | 0.000000 | 0.796962 | 0 | 0 |

Mỗi mean gồm 51 tài khoản symbol–block riêng, không phải portfolio; AS − reference là thay đổi kinh tế do scenario, không là predictive lift AS−B. Cả 12 scenarios, chín classifiers và continuous hold được giữ trong CSV. Hold có 51 cycles, classifiers có 102 cycles; không gán classification scores mới. Target/predictions/labels không đổi. Kết quả mô tả sau inference; không chứng nhận execution hoặc profitability.

Lịch và giới hạn nguồn theo T18: [báo cáo căn cứ](../execution_evidence_v1/report.md). Giữ 10 cờ unit HVN, không tự đổi thành CASH hoặc áp một chế độ phiên cho toàn giai đoạn. Maturity thuộc chiều T+2; clock_time null. Đơn vị Volume/hệ số giá/corporate actions chưa đủ provenance, nên lot/cap là giả định điều kiện. all_entries_missed không là cận dưới toán học. Reference chưa bao gồm mọi thuế; sell_charge_10bp tách riêng theo giả định cá nhân cư trú. Không thay code/policy/ledger lịch sử, không ghi paper/, không fit hoặc gọi API.

L=3 chỉ là ba observed bars gồm entry, tương đương exit sau entry hai phiên; close chỉ phù hợp settlement nếu được phân bổ và khớp lệnh. Không có so sánh horizon để kết luận tối ưu. Hai cutoffs/account cách nhau 57 observed sessions nên kết quả pending/on-demand trên mẫu này ít kiểm tra được nhu cầu tái dùng tiền nhanh. Tail cố định tối đa năm bars; residual shares được MTM, pending receivables thuộc wealth. report.json ghi các kiểm tra nguồn, reference từng dòng và oracle cash/shares/fees/maturity; logs là mô phỏng. R15 còn action bản thảo/response và locators sau gate hệ thống.
