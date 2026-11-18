package com.lawwiz.business.review;

import java.math.BigInteger;
import java.util.LinkedHashSet;
import java.util.List;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Resolve report follow-up context while enforcing user, task and risk ownership. */
@Service
public class ReportContexts {
    /** A short report finding without the original contract or citation snapshot. */
    public record Finding(String riskLevel, String title, String description, String suggestion) {}

    public record Context(String contractTitle, String summary, String riskLabel, String riskDescription,
                          String clauseText, String originalReference, String sourceType, boolean isDismissed,
                          List<Finding> findings) {}

    private final ReportContextMapper reports;
    private final ObjectMapper json;

    ReportContexts(ReportContextMapper reports, ObjectMapper json) {
        this.reports = reports;
        this.json = json;
    }

    public Context load(BigInteger owner, BigInteger taskId, BigInteger riskId) {
        return load(owner, taskId, riskId, false);
    }

    /** Include a bounded list of active findings when answering about the whole report. */
    public Context loadForAnswer(BigInteger owner, BigInteger taskId, BigInteger riskId) {
        return load(owner, taskId, riskId, true);
    }

    private Context load(BigInteger owner, BigInteger taskId, BigInteger riskId, boolean includeFindings) {
        if (taskId == null) {
            return null;
        }
        var report = reports.find(taskId);
        if (report == null) {
            throw new ApiError(40401, "审查任务不存在");
        }
        if (!report.userId().equals(owner)) {
            throw new ApiError(40301, "无权访问该审查任务");
        }
        if ("failed".equals(report.status())) {
            throw new ApiError(40907, "审查任务失败");
        }
        if (!"succeeded".equals(report.status())) {
            throw new ApiError(40906, "审查任务尚未完成");
        }
        if (report.reportId() == null) {
            throw new ApiError(40401, "审查报告不存在");
        }
        String summary = ApiValues.limit(report.summary(), 800);
        if (riskId == null) {
            var findings = includeFindings ? reports.findings(taskId) : List.<Finding>of();
            return new Context(report.contractTitle(), summary, null, null, null, null, null, false, findings);
        }
        var risk = reports.risk(taskId, riskId);
        if (risk == null) {
            throw new ApiError(40401, "风险点不存在");
        }
        String label = risk.clauseTitle();
        if (label == null || label.isEmpty()) {
            label = risk.riskCategory() == null ? "风险项 #" + riskId : risk.riskCategory();
        }
        return new Context(report.contractTitle(), summary, label, ApiValues.limit(risk.description(), 800),
                ApiValues.limit(risk.clauseText(), 1200), references(risk), risk.sourceType(), risk.dismissed(), List.of());
    }

    private String references(ReportContextMapper.Risk risk) {
        var references = new LinkedHashSet<String>();
        add(references, risk.legalBasis());
        if (risk.sourceSnapshot() != null) {
            var snapshot = json.readTree(risk.sourceSnapshot());
            var citations = snapshot.path("citations");
            if (citations.isArray() && !citations.isEmpty()) {
                for (int index = 0; index < Math.min(citations.size(), 3); index++) {
                    addFields(references, citations.path(index));
                }
            } else {
                addFields(references, snapshot);
            }
        }
        return references.isEmpty() ? null : ApiValues.limit(String.join("\n", references), 1500);
    }

    private void addFields(LinkedHashSet<String> references, JsonNode source) {
        for (String field : java.util.List.of("law_name", "article_no", "quoted_text")) {
            add(references, source.path(field).asString(null));
        }
    }

    private void add(LinkedHashSet<String> references, String value) {
        if (value != null && !value.isBlank()) {
            references.add(ApiValues.limit(value, 700));
        }
    }
}
