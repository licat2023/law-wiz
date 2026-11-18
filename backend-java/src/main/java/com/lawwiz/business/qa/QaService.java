package com.lawwiz.business.qa;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.api.BackgroundTasks;
import com.lawwiz.business.inference.InferenceClient;
import com.lawwiz.business.review.ReportContexts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Own the QA history, authorize report context, and persist inference results and citations. */
@Service
class QaService {
    record Location(String reviewTaskId, String riskPointId, String contractTitle, String riskLabel, boolean available) {}
    record Submission(String userMessageId, String assistantMessageId, String status) {}
    record Page<T>(List<T> items, int page, int pageSize, long total) {}
    record Citation(String documentId, String knowledgeBaseChunkId,
                    String lawName, String articleNo, String quotedText, java.math.BigDecimal relevanceScore) {}
    record Message(String messageId, String role, String content, boolean hasCitation, List<Citation> citations,
                   String modelName, Integer latencyMs, String createdAt) {}

    private static final Logger LOGGER = LoggerFactory.getLogger(QaService.class);
    private static final String FAILURE = "回答生成失败，请稍后重试。";
    private static final Set<String> SORTS = Set.of("-last_message_at", "last_message_at", "-created_at", "created_at");
    private final QaMapper mapper;
    private final ReportContexts reports;
    private final InferenceClient inference;
    private final TransactionTemplate transactions;
    private final BackgroundTasks background;
    private final ObjectMapper json;
    private final Map<BigInteger, QaAnswerStream> activeAnswers = new ConcurrentHashMap<>();

    QaService(QaMapper mapper, ReportContexts reports, InferenceClient inference,
              TransactionTemplate transactions, BackgroundTasks background, ObjectMapper json) {
        this.mapper = mapper;
        this.reports = reports;
        this.inference = inference;
        this.transactions = transactions;
        this.background = background;
        this.json = json;
    }

    Map<String, Object> create(BigInteger owner, String title, BigInteger task, BigInteger risk) {
        if (risk != null && task == null) {
            throw new ApiError(40001, "选择风险项时须指定审查任务");
        }
        return transactions.execute(status -> {
            var context = reports.load(owner, task, risk);
            String storedTitle = title;
            if (context != null && (title == null || title.isEmpty())) {
                String label = first(context.riskLabel(), first(context.contractTitle(), "报告 #" + task));
                storedTitle = ApiValues.limit("审查追问 · " + label, 200);
            }
            var values = new HashMap<String, Object>();
            values.put("userId", owner);
            values.put("taskId", task);
            values.put("riskId", risk);
            values.put("title", storedTitle);
            mapper.create(values);
            return summary(mapper.find(generatedId(values)), context);
        });
    }

    Page<Map<String, Object>> list(BigInteger owner, String filter, String sort, int page, int size) {
        long offset = ApiValues.offset(page, size);
        if (!SORTS.contains(sort)) {
            throw new ApiError(40001, "sort 取值不合法");
        }
        var result = mapper.list(owner, filter, sort, size, offset).stream().map(session -> {
            var item = fields(session);
            item.put("last_message_at", ApiValues.timestamp(session.lastMessageAt()));
            return item;
        }).toList();
        return new Page<>(result, page, size, mapper.countSessions(owner, filter));
    }

    Map<String, Object> detail(BigInteger owner, BigInteger id, int page, int size) {
        var session = owned(owner, mapper.find(id));
        var messages = mapper.messages(id, size, ApiValues.offset(page, size));
        Map<BigInteger, List<Citation>> byMessage = new HashMap<>();
        if (!messages.isEmpty()) {
            for (var citation : mapper.citations(messages.stream().map(QaMapper.Message::id).toList())) {
                JsonNode snapshot = citation.sourceSnapshot() == null ? json.createObjectNode() : json.readTree(citation.sourceSnapshot());
                byMessage.computeIfAbsent(citation.qaMessageId(), ignored -> new ArrayList<>()).add(new Citation(
                        citation.documentId(), citation.chunkId(),
                        first(snapshot.path("law_name").asString(null), snapshot.path("title").asString(null)),
                        snapshot.path("article_no").asString(null),
                        first(citation.quotedText(), snapshot.path("quoted_text").asString(null)),
                        citation.relevanceScore()));
            }
        }
        var items = messages.stream().map(row -> new Message(row.id().toString(), row.role(), row.content(),
                row.hasCitation(), byMessage.getOrDefault(row.id(), List.of()), row.modelName(),
                row.latencyMs(), ApiValues.timestamp(row.createdAt()))).toList();
        ReportContexts.Context report;
        try {
            report = reports.load(owner, session.reviewTaskId(), session.riskPointId());
        } catch (ApiError error) {
            report = null;
        }
        var result = summary(session, report);
        result.put("messages", new Page<>(items, page, size, mapper.countMessages(id)));
        return result;
    }

    Submission ask(BigInteger owner, BigInteger sessionId, String question, String requestId) {
        var stream = new QaAnswerStream();
        var submission = transactions.execute(status -> {
            var session = owned(owner, mapper.lock(sessionId));
            if (!"active".equals(session.status())) {
                throw new ApiError(40909, "会话已归档，无法继续提问");
            }
            reports.load(owner, session.reviewTaskId(), session.riskPointId());
            BigInteger questionId = insertMessage(sessionId, "user", question);
            BigInteger answerId = insertMessage(sessionId, "assistant", "");
            mapper.countTurn(sessionId, ApiValues.limit(question, 50));
            registerAnswerStream(answerId, stream);
            return new Submission(questionId.toString(), answerId.toString(), "pending");
        });
        BigInteger answerId = ApiValues.id(submission.assistantMessageId());
        BigInteger questionId = ApiValues.id(submission.userMessageId());
        background.submit(
                () -> answer(owner, sessionId, questionId, answerId, question, requestId, stream),
                () -> {
                    failed(answerId, "回答生成失败：服务繁忙，请稍后重试");
                    finishStream(answerId, stream);
                });
        return submission;
    }

    /** Register the stream before releasing the session lock, and discard it on rollback. */
    private void registerAnswerStream(BigInteger answerId, QaAnswerStream stream) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void beforeCommit(boolean readOnly) {
                activeAnswers.put(answerId, stream);
            }

            @Override
            public void afterCompletion(int status) {
                if (status != STATUS_COMMITTED) activeAnswers.remove(answerId, stream);
            }
        });
    }

    /** A subscription observes the existing background task; it cannot start a new turn. */
    SseEmitter stream(BigInteger owner, BigInteger sessionId, BigInteger answerId) {
        owned(owner, mapper.find(sessionId));
        if (mapper.assistantMessage(sessionId, answerId) == null) {
            throw new ApiError(40402, "问答消息不存在");
        }
        var stream = activeAnswers.get(answerId);
        return stream == null ? QaAnswerStream.finishedSubscription() : stream.subscribe();
    }

    /** Toggle archive membership without changing the conversation history. */
    void setArchived(BigInteger owner, BigInteger id, boolean archived) {
        transactions.executeWithoutResult(ignored -> {
            var session = owned(owner, mapper.lock(id));
            String next = archived ? "archived" : "active";
            if (!next.equals(session.status())) mapper.setStatus(id, next);
        });
    }

    /** Remove an owned archived conversation, including its messages and citations. */
    void deleteArchived(BigInteger owner, BigInteger id) {
        transactions.executeWithoutResult(ignored -> {
            var session = owned(owner, mapper.lock(id));
            if (!"archived".equals(session.status())) {
                throw new ApiError(40911, "请先归档会话再彻底删除");
            }
            if (mapper.pendingAnswers(id).stream().anyMatch(activeAnswers::containsKey)) {
                throw new ApiError(40911, "请等待回答完成后再彻底删除");
            }
            mapper.deleteCitations(id);
            mapper.deleteMessages(id);
            mapper.deleteSession(id);
        });
    }

    private void answer(BigInteger owner, BigInteger sessionId, BigInteger questionId,
                        BigInteger answerId, String question, String requestId, QaAnswerStream stream) {
        try {
            var session = owned(owner, mapper.find(sessionId));
            var report = reports.loadForAnswer(owner, session.reviewTaskId(), session.riskPointId());
            Map<String, Object> payload = new HashMap<>();
            payload.put("question", question);
            if (report != null) {
                var history = new ArrayList<>(mapper.recent(sessionId, questionId));
                Collections.reverse(history);
                payload.put("report", report);
                payload.put("history", history);
            }
            long start = System.nanoTime();
            JsonNode result = inference.qa(payload, requestId, "qa_" + answerId, stream::append);
            store(sessionId, answerId, result, (int) TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start));
        } catch (ApiError error) {
            failed(answerId, "回答生成失败：" + error.getMessage());
        } catch (RuntimeException error) {
            LOGGER.warn("Could not answer message {} for request {}", answerId, requestId, error);
            failed(answerId, FAILURE);
        } finally {
            finishStream(answerId, stream);
        }
    }

    private void finishStream(BigInteger answerId, QaAnswerStream stream) {
        try {
            stream.finish();
        } finally {
            activeAnswers.remove(answerId, stream);
        }
    }

    private void store(BigInteger sessionId, BigInteger answerId, JsonNode result, int latency) {
        var valid = result.path("citations").valueStream()
                .filter(source -> !source.path("document_id").asString("").isEmpty()
                        && !source.path("knowledge_base_chunk_id").asString("").isEmpty())
                .toList();
        transactions.executeWithoutResult(status -> {
            if (mapper.lock(sessionId) == null) return;
            int updated = mapper.finish(answerId, result.path("answer").asString().strip(), !valid.isEmpty(),
                    ApiValues.limit(result.path("model_name").asString(null), 64), latency);
            if (updated == 1) {
                for (JsonNode source : valid) {
                    mapper.cite(answerId, source.path("knowledge_base_id").asString(null),
                            source.path("document_id").asString(), source.path("knowledge_base_chunk_id").asString(),
                            source.path("revision").asString(null), source.path("index_revision_id").asString(null),
                            source.path("quoted_text").asString(null), source.path("relevance_score").decimalValue(null),
                            source.toString());
                }
            }
        });
    }

    private void failed(BigInteger answerId, String message) {
        try {
            mapper.finish(answerId, message, false, null, null);
        } catch (RuntimeException error) {
            LOGGER.error("Could not persist failure for QA message {}", answerId, error);
        }
    }

    private QaMapper.Session owned(BigInteger owner, QaMapper.Session session) {
        if (session == null) {
            throw new ApiError(40402, "问答会话不存在");
        }
        if (!owner.equals(session.userId())) {
            throw new ApiError(40301, "无权访问该会话");
        }
        return session;
    }

    private BigInteger insertMessage(BigInteger session, String role, String content) {
        var values = new HashMap<String, Object>(Map.of("sessionId", session, "role", role, "content", content));
        mapper.createMessage(values);
        return generatedId(values);
    }

    private BigInteger generatedId(Map<String, Object> values) {
        return ApiValues.id(values.get("id").toString());
    }

    private static Map<String, Object> fields(QaMapper.Session session) {
        var result = new LinkedHashMap<String, Object>();
        result.put("session_id", session.id().toString());
        result.put("title", session.title());
        result.put("status", session.status());
        result.put("message_count", session.messageCount());
        result.put("created_at", ApiValues.timestamp(session.createdAt()));
        return result;
    }

    private static Map<String, Object> summary(QaMapper.Session session, ReportContexts.Context report) {
        var result = fields(session);
        Location location = session.reviewTaskId() == null ? null : new Location(
                session.reviewTaskId().toString(), session.riskPointId() == null ? null : session.riskPointId().toString(),
                report == null ? null : report.contractTitle(), report == null ? null : report.riskLabel(), report != null);
        result.put("review_context", location);
        return result;
    }

    private static String first(String first, String second) {
        return first == null || first.isEmpty() ? second : first;
    }
}
