package com.lawwiz.business.review;

import java.math.BigInteger;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

/** Find the minimum report data required by the authorized follow-up workflow. */
@Mapper
interface ReportContextMapper {
    record Report(BigInteger userId, String status, String contractTitle, BigInteger reportId, String summary) {}
    record Risk(String clauseTitle, String riskCategory, String description, String clauseText,
                String legalBasis, String sourceType, boolean dismissed, String sourceSnapshot) {}

    @Select("""
            SELECT task.user_id, task.status, contract.title AS contract_title, report.id AS report_id, report.summary
            FROM review_task task
            LEFT JOIN contract ON contract.id = task.contract_id
            LEFT JOIN review_report report ON report.review_task_id = task.id AND report.deleted_at IS NULL
            WHERE task.id = #{id} AND task.deleted_at IS NULL
            """)
    Report find(BigInteger id);

    @Select("""
            SELECT risk_level, COALESCE(NULLIF(clause_title, ''), risk_category) AS title,
                   LEFT(description, 480) AS description, LEFT(suggestion, 480) AS suggestion
            FROM risk_point
            WHERE review_task_id = #{taskId} AND deleted_at IS NULL AND is_dismissed = FALSE
            ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id
            LIMIT 8
            """)
    List<ReportContexts.Finding> findings(BigInteger taskId);

    @Select("""
            SELECT clause_title, risk_category, description, clause_text, legal_basis, source_type,
                   is_dismissed AS dismissed, source_snapshot
            FROM risk_point WHERE review_task_id = #{taskId} AND id = #{riskId} AND deleted_at IS NULL
            """)
    Risk risk(BigInteger taskId, BigInteger riskId);
}
