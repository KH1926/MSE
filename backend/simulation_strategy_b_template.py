from __future__ import annotations

from typing import Any


class BTeamSimulationStrategy:
    """
    B 侧策略模板：
    - 保持 run(conn, payload) 签名不变
    - 返回字段需包含：
      scenario / processed_work_orders / processed_tasks / events_created / quality_records_created
    """

    strategy_name = "b_team_template"

    def run(self, conn, payload: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "请在 BTeamSimulationStrategy.run 中实现仿真策略，并返回约定字段。"
        )

