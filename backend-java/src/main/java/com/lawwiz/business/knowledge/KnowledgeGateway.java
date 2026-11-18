package com.lawwiz.business.knowledge;

import java.math.BigInteger;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import com.lawwiz.business.api.ApiError;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Connect to the default knowledge base using separate reader and writer grants. */
@Component
class KnowledgeGateway {
    private final RestClient client;
    private final String defaultId;
    private final String reader;
    private final String writer;
    private final Set<String> admins;
    private final ObjectMapper json;

    KnowledgeGateway(ObjectMapper json,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_BASE_URL:}") String endpoint,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_DEFAULT_ID:}") String defaultId,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_SERVICE_KEY:}") String reader,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_WRITER_KEY:}") String writer,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_ADMIN_USER_IDS:[]}") String admins) {
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(5)).build());
        factory.setReadTimeout(Duration.ofSeconds(60));
        client = endpoint.isBlank() ? null : RestClient.builder().baseUrl(endpoint).requestFactory(factory).build();
        this.defaultId = defaultId;
        this.reader = reader;
        this.writer = writer;
        this.admins = json.readTree(admins).valueStream().map(JsonNode::asString).collect(Collectors.toUnmodifiableSet());
        this.json = json;
    }

    void requireWriter(BigInteger user) {
        if (writer.isBlank() || writer.equals(reader) || !admins.contains(user.toString())) {
            throw new ApiError(40301, "仅配置的知识库管理员可执行此操作");
        }
    }

    JsonNode get(String requestId, Map<String, ?> params, String... segments) {
        return exchange(HttpMethod.GET, reader, requestId, params, null, null, segments);
    }

    JsonNode search(String requestId, Object body) {
        return exchange(HttpMethod.POST, reader, requestId, Map.of(), body, null, "search");
    }

    JsonNode write(BigInteger user, String requestId, Object body, String idempotency, String... segments) {
        requireWriter(user);
        return exchange(HttpMethod.POST, writer, requestId, Map.of(), body, idempotency, segments);
    }

    private JsonNode exchange(HttpMethod method, String token, String requestId, Map<String, ?> params,
                              Object body, String idempotency, String... segments) {
        if (client == null || token.isBlank() || defaultId.isBlank()) {
            throw new ApiError(50303, "知识库服务未配置");
        }
        try {
            var specification = client.method(method).uri(builder -> {
                builder.pathSegment("api", "knowledge-bases", defaultId);
                Arrays.stream(segments).forEach(builder::pathSegment);
                params.forEach(builder::queryParam);
                return builder.build();
            }).headers(headers -> {
                headers.setBearerAuth(token);
                headers.set("X-Request-ID", requestId);
                if (idempotency != null) {
                    headers.set("Idempotency-Key", idempotency);
                }
            });
            if (body != null) {
                JsonNode request = json.valueToTree(body);
                specification.contentType(MediaType.APPLICATION_JSON).body(request);
            }
            JsonNode result = specification.retrieve().body(JsonNode.class);
            if (result == null || result.path("code").asInt(-1) != 0 || !result.path("data").isObject()) {
                throw new ApiError(50303, "知识库响应结构不合法");
            }
            return result.path("data");
        } catch (RestClientResponseException error) {
            throw switch (error.getStatusCode().value()) {
                case 400, 413, 415, 422 -> new ApiError(40001, "知识库请求参数不合法");
                case 404 -> new ApiError(40403, "知识文档不存在");
                case 409 -> new ApiError(40908, "知识文档重复或修订冲突");
                default -> new ApiError(50303, "知识库服务调用失败");
            };
        } catch (RestClientException error) {
            throw new ApiError(50303, "知识库服务暂不可用");
        }
    }
}
