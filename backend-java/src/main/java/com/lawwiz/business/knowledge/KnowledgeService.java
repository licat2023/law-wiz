package com.lawwiz.business.knowledge;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.files.ContentKeys;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Map the legacy public knowledge API to independently managed documents and indexes. */
@Service
class KnowledgeService {
    record Page(List<Map<String, Object>> items, int page, int pageSize, long total) {}

    private static final Set<String> SORTS = Set.of("created_at", "title", "effective_date");
    private final KnowledgeGateway gateway;
    private final ObjectMapper json;

    KnowledgeService(KnowledgeGateway gateway, ObjectMapper json) {
        this.gateway = gateway;
        this.json = json;
    }

    Object create(BigInteger owner, String requestId, KnowledgeController.Document payload) {
        gateway.requireWriter(owner);
        int tier = payload.corpusTier() == null ? 1 : payload.corpusTier();
        String hash = hash(payload.content());
        JsonNode metadata = json.valueToTree(payload);
        var attributes = json.createObjectNode();
        for (var entry : metadata.properties()) {
            if (!Set.of("title", "content").contains(entry.getKey())) {
                attributes.set(entry.getKey(), entry.getValue());
            }
        }
        attributes.put("corpus_tier", tier).put("document_profile", "legal_article").put("content_hash", hash);
        var result = gateway.write(owner, requestId,
                Map.of("title", payload.title(), "content", payload.content(), "metadata", attributes), hash, "documents");
        return Map.of("document_id", result.path("id").asString(), "content_hash", hash,
                "char_count", length(payload.content()), "index_status", indexStatus(result.path("status").asString()),
                "chunk_count", result.path("chunk_count").asInt(0));
    }

    Object index(BigInteger owner, String requestId, String id, boolean force) {
        gateway.requireWriter(owner);
        var document = gateway.get(requestId, Map.of(), "documents", id);
        String status = document.path("status").asString();
        if (!force && Set.of("pending", "parsing", "chunking", "embedding").contains(status)) {
            return Map.of("document_id", id, "index_status", indexStatus(status),
                    "task_id", document.path("current_job_id").asString(id));
        }
        var job = gateway.write(owner, requestId, Map.of("revision", document.path("revision")),
                null, "documents", id, "indexes");
        return Map.of("document_id", id, "index_status", indexStatus(job.path("status").asString()),
                "task_id", job.path("id").asString());
    }

    Page list(String requestId, int page, int size, String type, Integer tier, String status, String law, String sort) {
        ApiValues.offset(page, size);
        if (!SORTS.contains(sort.startsWith("-") ? sort.substring(1) : sort)) {
            throw new ApiError(40001, "sort 取值不合法");
        }
        var params = new LinkedHashMap<String, Object>(Map.of("page", page, "page_size", size, "sort", sort));
        put(params, "doc_type", type);
        put(params, "corpus_tier", tier);
        put(params, "status", "indexed".equals(status) ? "ready" : status);
        put(params, "law_name", law);
        var result = gateway.get(requestId, params, "documents");
        var items = result.path("items").valueStream().map(this::listItem).toList();
        return new Page(items, page, size, result.path("total").asLong(0));
    }

    Object detail(String requestId, String id) {
        var document = gateway.get(requestId, Map.of(), "documents", id);
        var chunks = gateway.get(requestId, Map.of("page", 1, "page_size", 20), "documents", id, "chunks");
        var data = listItem(document);
        var metadata = document.path("metadata");
        String content = document.path("content").asString("");
        for (String field : List.of("chapter_path", "abolished_date", "source", "source_url", "indexed_at")) {
            data.put(field, metadata.path(field).asString(null));
        }
        data.put("revision", metadata.path("revision").asString(document.path("revision").asString(null)));
        data.put("content_hash", metadata.path("content_hash").asString(hash(content)));
        data.put("content", content);
        data.put("char_count", length(content));
        data.put("chunks", chunks.path("items").valueStream().map(this::chunk).toList());
        return data;
    }

    Object search(String requestId, String query, int limit, String type, Integer tier, boolean includeAbolished) {
        if (query.isBlank() || limit < 1 || limit > 20) {
            throw new ApiError(40001, "检索参数不合法");
        }
        var payload = new LinkedHashMap<String, Object>(
                Map.of("query", query, "top_k", limit, "include_abolished", includeAbolished));
        put(payload, "doc_type", type);
        put(payload, "corpus_tier", tier);
        var result = gateway.search(requestId, payload);
        return Map.of("query", query, "items", result.path("items").valueStream().map(this::hit).toList());
    }

    private Map<String, Object> listItem(JsonNode doc) {
        var metadata = doc.path("metadata");
        var item = new LinkedHashMap<String, Object>();
        item.put("document_id", doc.path("id").asString());
        item.put("doc_type", metadata.path("doc_type").asString("law"));
        item.put("corpus_tier", metadata.path("corpus_tier").asInt(1));
        item.put("title", doc.path("title").asString());
        item.put("law_name", metadata.path("law_name").asString(null));
        item.put("article_no", metadata.path("article_no").asString(null));
        item.put("effective_date", metadata.path("effective_date").asString(null));
        item.put("index_status", indexStatus(doc.path("status").asString()));
        item.put("chunk_count", doc.path("chunk_count").asInt(0));
        item.put("created_at", doc.path("created_at").asString());
        return item;
    }

    private Map<String, Object> chunk(JsonNode chunk) {
        var result = textFields(chunk, chunk.path("article_no").asString(null));
        result.put("chunk_no", chunk.path("chunk_no").asInt());
        return result;
    }

    private Map<String, Object> hit(JsonNode hit) {
        var metadata = hit.path("metadata");
        var result = textFields(hit, metadata.path("article_no").asString(null));
        result.put("chunk_id", hit.path("chunk_id").asString());
        result.put("document_id", hit.path("document_id").asString());
        result.put("law_name", metadata.path("law_name").asString(hit.path("title").asString()));
        result.put("effective_date", metadata.path("effective_date").asString(null));
        result.put("score", hit.path("score").asDouble());
        return result;
    }

    private Map<String, Object> textFields(JsonNode node, String article) {
        var values = new LinkedHashMap<String, Object>();
        values.put("article_no", article);
        values.put("chunk_type", article == null || article.isEmpty() ? "paragraph" : "article");
        values.put("char_start", node.path("char_start").asInt());
        values.put("char_end", node.path("char_end").asInt());
        values.put("content", node.path("content").asString());
        return values;
    }

    private static String indexStatus(String status) {
        return switch (status) {
            case "ready" -> "indexed";
            case "parsing", "chunking", "embedding" -> "indexing";
            default -> status;
        };
    }

    private static void put(Map<String, Object> map, String key, Object value) {
        if (value != null) {
            map.put(key, value);
        }
    }

    private static String hash(String content) {
        return ContentKeys.sha256(content.getBytes(StandardCharsets.UTF_8));
    }

    private static int length(String text) {
        return text.codePointCount(0, text.length());
    }
}
