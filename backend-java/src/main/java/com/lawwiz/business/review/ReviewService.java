package com.lawwiz.business.review;

import java.math.BigInteger;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.api.BackgroundTasks;
import com.lawwiz.business.files.BusinessFiles;
import com.lawwiz.business.inference.InferenceClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Own the contract review workflow, business states and persisted report output. */
@Service
class ReviewService {
    record Counts(int high, int medium, int low) {}
    record Page(List<Item> items, int page, int pageSize, long total) {}
    record Item(String taskId, String contractTitle, String status, Counts counts, String createdAt, String finishedAt) {}
    record Download(String filename, byte[] bytes) {}
    record TaskView(String taskId, String status, String stage, int progress, String errorCode,
                    String errorMessage, String startedAt, String finishedAt, String createdAt) {}
    record PointView(String id, String riskLevel, String riskCategory, String clauseTitle, String clauseText,
                     Integer charStart, Integer charEnd, String description, String suggestion, String legalBasis,
                     String sourceType, java.math.BigDecimal confidence, boolean isDismissed) {}

    private static final Logger LOGGER = LoggerFactory.getLogger(ReviewService.class);
    private static final int MAX_INFERENCE_TEXT = 200_000;
    private static final Set<String> LEVELS = Set.of("high", "medium", "low");
    private static final Set<String> TYPES = Set.of("retrieved_law", "rule", "llm_inference");
    private static final Set<String> STATUSES = Set.of("pending", "processing", "succeeded", "failed");
    private static final Set<String> SORTS = Set.of("created_at", "-created_at", "finished_at", "-finished_at");
    private final ReviewMapper mapper;
    private final BusinessFiles files;
    private final InferenceClient inference;
    private final ReviewPdf pdf;
    private final TransactionTemplate transactions;
    private final BackgroundTasks background;
    private final ObjectMapper json;

    ReviewService(ReviewMapper mapper, BusinessFiles files, InferenceClient inference, ReviewPdf pdf,
                  TransactionTemplate transactions, BackgroundTasks background, ObjectMapper json) {
        this.mapper = mapper;
        this.files = files;
        this.inference = inference;
        this.pdf = pdf;
        this.transactions = transactions;
        this.background = background;
        this.json = json;
    }

    TaskView create(BigInteger owner, BigInteger fileId, String title, boolean force, String requestId) {
        var source = files.source(fileId);
        var task = transactions.execute(status -> {
            if (mapper.lockOwner(owner) == null) {
                throw new ApiError(40101, "访问令牌无效或已过期");
            }
            var version = mapper.findVersion(owner, fileId);
            if (version == null) {
                version = createVersion(owner, fileId, ApiValues.limit(fallback(title, fallback(source.name(), "未命名合同")), 200));
            }
            if (!force && mapper.hasRunningTask(version.id())) {
                throw new ApiError(40905, "该文件正在审查中，请等待完成或使用 force 重试");
            }
            var values = new HashMap<String, Object>(Map.of("owner", owner, "contract", version.contractId(), "version", version.id()));
            mapper.createTask(values);
            return mapper.task(generated(values));
        });
        background.submit(() -> run(task, requestId), () -> fail(task.id(), new ApiError(42901, "服务繁忙，请稍后重试")));
        return view(task);
    }

    TaskView status(BigInteger owner, BigInteger id) {
        return view(owned(owner, id));
    }

    Page list(BigInteger owner, String status, String sort, int page, int size) {
        long offset = ApiValues.offset(page, size);
        if (status != null && !STATUSES.contains(status)) {
            throw new ApiError(40001, "status 取值不合法");
        }
        if (!SORTS.contains(sort)) {
            throw new ApiError(40001, "sort 取值不合法");
        }
        var items = mapper.list(owner, status, sort, size, offset).stream().map(task -> new Item(task.id().toString(),
                title(task), task.status(), savedCounts(mapper.report(task.id())), ApiValues.timestamp(task.createdAt()),
                ApiValues.timestamp(task.finishedAt()))).toList();
        return new Page(items, page, size, mapper.count(owner, status));
    }

    Map<String, Object> result(BigInteger owner, BigInteger id) {
        var task = finished(owner, id);
        var risks = mapper.points(id).stream().map(this::point).toList();
        var report = mapper.report(id);
        var data = new LinkedHashMap<String, Object>();
        data.put("task_id", id.toString());
        data.put("contract_title", title(task));
        data.put("summary", report == null ? null : report.summary());
        data.put("counts", countRisks(risks.stream().map(PointView::riskLevel).toList()));
        data.put("extracted_terms", task.extractedTerms() == null ? null : json.readTree(task.extractedTerms()));
        data.put("risk_points", risks);
        return data;
    }

    Download download(BigInteger owner, BigInteger id) {
        finished(owner, id);
        var report = mapper.report(id);
        if (report == null || report.fileObjectId() == null) {
            throw new ApiError(40401, "审查报告不存在");
        }
        BusinessFiles.Source source;
        try {
            source = files.source(report.fileObjectId());
        } catch (ApiError error) {
            throw new ApiError(40401, "审查报告文件不存在");
        }
        return new Download(fallback(source.name(), "review-" + id + ".pdf"), files.read(source));
    }

    PointView dismiss(BigInteger owner, BigInteger id, BigInteger risk, boolean dismissed) {
        return transactions.execute(status -> {
            owned(owner, id);
            if (mapper.point(id, risk) == null) {
                throw new ApiError(40401, "风险点不存在");
            }
            mapper.dismiss(id, risk, dismissed);
            return point(mapper.point(id, risk));
        });
    }

    private void run(ReviewMapper.Task task, String requestId) {
        try {
            if (mapper.begin(task.id()) != 1) {
                return;
            }
            String text = extract(task);
            mapper.stage(task.id(), "analyze", 85);
            var result = inference.review(Map.of("plain_text", ApiValues.limit(text, MAX_INFERENCE_TEXT),
                            "risk_rules", rules(text)),
                    requestId, "review_" + task.id());
            var risks = result.path("risk_points").valueStream().filter(JsonNode::isObject).toList();
            Counts counts = countRisks(risks.stream().map(risk -> level(risk)).toList());
            mapper.stage(task.id(), "report", 95);
            String title = fallback(title(task), "合同 #" + task.contractVersionId());
            String summary = summary(counts);
            byte[] report = pdf.render(title, summary, result.path("extracted_terms"), risks);
            BigInteger file = files.saveReport(task.userId(), ApiValues.limit(title, 240) + "-审查报告.pdf", report);
            transactions.executeWithoutResult(status -> {
                if (mapper.finish(task.id(), result.path("extracted_terms").toString(), json.createObjectNode()
                        .set("contract_review", result).toString()) != 1) {
                    throw new ApiError(40907, "审查任务状态已变更");
                }
                for (JsonNode risk : risks) {
                    mapper.insertPoint(riskValues(task.id(), risk));
                }
                mapper.insertReport(task.id(), file, summary, counts.high(), counts.medium(), counts.low());
            });
        } catch (ApiError error) {
            fail(task.id(), error);
        } catch (RuntimeException error) {
            LOGGER.error("Review {} failed for request {}", task.id(), requestId, error);
            fail(task.id(), new ApiError(50000, "服务器内部错误，审查未能完成"));
        }
    }

    private String extract(ReviewMapper.Task task) {
        var version = mapper.version(task.contractVersionId());
        if (version == null || version.fileObjectId() == null) {
            throw new ApiError(40907, "合同版本不存在，无法审查");
        }
        if (version.plainText() != null && !version.plainText().isEmpty()) {
            return version.plainText();
        }
        var source = files.source(version.fileObjectId());
        var extracted = ContractText.extract(files.read(source), source.mime());
        mapper.storeText(version.id(), extracted.text(), extracted.pages());
        return extracted.text();
    }

    private List<Map<String, Object>> rules(String text) {
        return mapper.rules().stream().filter(rule -> rule.matchKeywords() != null
                && Arrays.stream(rule.matchKeywords().split(",")).map(String::strip)
                        .anyMatch(word -> !word.isEmpty() && text.contains(word)))
                .map(rule -> {
                    var result = new HashMap<String, Object>();
                    result.put("risk_level", rule.riskLevel());
                    result.put("risk_category", rule.category());
                    result.put("description", rule.conclusion());
                    result.put("suggestion", rule.suggestion());
                    result.put("legal_basis", rule.legalBasis());
                    result.put("source_type", "rule");
                    return (Map<String, Object>) result;
                }).toList();
    }

    private Map<String, Object> riskValues(BigInteger id, JsonNode risk) {
        var values = new HashMap<String, Object>();
        values.put("id", id);
        values.put("level", level(risk));
        values.put("category", ApiValues.limit(risk.path("risk_category").asString(null), 32));
        values.put("title", ApiValues.limit(risk.path("clause_title").asString(null), 200));
        values.put("text", risk.path("clause_text").asString(null));
        values.put("start", risk.path("char_start").isIntegralNumber() ? risk.path("char_start").intValue() : null);
        values.put("end", risk.path("char_end").isIntegralNumber() ? risk.path("char_end").intValue() : null);
        values.put("description", fallback(risk.path("description").asString(null), "模型未给出说明"));
        values.put("suggestion", risk.path("suggestion").asString(null));
        values.put("basis", risk.path("legal_basis").asString(null));
        String type = risk.path("source_type").asString("");
        values.put("type", TYPES.contains(type) ? type : "llm_inference");
        values.put("confidence", risk.path("confidence").decimalValue(null));
        values.put("snapshot", risk.toString());
        JsonNode source = risk.path("citations").path(0);
        String document = source.path("document_id").asString(null);
        values.put("service", document == null ? null : "knowledge_base");
        values.put("document", document);
        values.put("chunk", source.path("knowledge_base_chunk_id").asString(null));
        values.put("revision", source.path("revision").asString(null));
        return values;
    }

    private void fail(BigInteger id, ApiError failure) {
        try {
            mapper.fail(id, Integer.toString(failure.code()), ApiValues.limit(failure.getMessage(), 500));
        } catch (RuntimeException error) {
            LOGGER.error("Could not persist failed review {}", id, error);
        }
    }

    private ReviewMapper.Version createVersion(BigInteger owner, BigInteger file, String title) {
        var contract = new HashMap<String, Object>(Map.of("owner", owner, "title", title));
        mapper.createContract(contract);
        BigInteger contractId = generated(contract);
        var version = new HashMap<String, Object>(Map.of("contract", contractId, "file", file, "owner", owner));
        mapper.createVersion(version);
        BigInteger versionId = generated(version);
        mapper.setVersion(contractId, versionId);
        return mapper.version(versionId);
    }

    private ReviewMapper.Task owned(BigInteger owner, BigInteger id) {
        var task = mapper.task(id);
        if (task == null) {
            throw new ApiError(40401, "审查任务不存在");
        }
        if (!owner.equals(task.userId())) {
            throw new ApiError(40301, "无权访问该审查任务");
        }
        return task;
    }

    private ReviewMapper.Task finished(BigInteger owner, BigInteger id) {
        var task = owned(owner, id);
        if ("failed".equals(task.status())) {
            throw new ApiError(40907, fallback(task.errorMessage(), "审查任务执行失败"));
        }
        if (!"succeeded".equals(task.status())) {
            throw new ApiError(40906, "审查任务尚未完成");
        }
        return task;
    }

    private TaskView view(ReviewMapper.Task task) {
        return new TaskView(task.id().toString(), task.status(), task.stage(), task.progress(), task.errorCode(),
                task.errorMessage(), ApiValues.timestamp(task.startedAt()), ApiValues.timestamp(task.finishedAt()),
                ApiValues.timestamp(task.createdAt()));
    }

    private PointView point(ReviewMapper.Point risk) {
        return new PointView(risk.id().toString(), risk.riskLevel(), risk.riskCategory(), risk.clauseTitle(),
                risk.clauseText(), risk.charStart(), risk.charEnd(), risk.description(), risk.suggestion(),
                risk.legalBasis(), risk.sourceType(), risk.confidence(), risk.isDismissed());
    }

    private String title(ReviewMapper.Task task) {
        return task.contractId() == null ? null : mapper.contractTitle(task.contractId());
    }

    private Counts savedCounts(ReviewMapper.Report report) {
        return report == null ? new Counts(0, 0, 0) : new Counts(report.highCount(), report.mediumCount(), report.lowCount());
    }

    private Counts countRisks(List<String> risks) {
        return new Counts(java.util.Collections.frequency(risks, "high"), java.util.Collections.frequency(risks, "medium"),
                java.util.Collections.frequency(risks, "low"));
    }

    private String level(JsonNode risk) {
        String level = risk.path("risk_level").asString("");
        return LEVELS.contains(level) ? level : "medium";
    }

    private String summary(Counts counts) {
        int total = counts.high() + counts.medium() + counts.low();
        return total == 0 ? "本次审查未发现风险点。" : "本合同共发现 %d 处风险，其中高风险 %d 处、中风险 %d 处、低风险 %d 处。"
                .formatted(total, counts.high(), counts.medium(), counts.low());
    }

    private BigInteger generated(Map<String, Object> values) {
        return ApiValues.id(values.get("id").toString());
    }

    private String fallback(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }
}
