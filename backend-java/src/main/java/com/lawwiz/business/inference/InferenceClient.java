package com.lawwiz.business.inference;

import java.net.http.HttpClient;
import java.time.Duration;

import com.lawwiz.business.api.ApiError;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Call the authenticated inference service and translate its failure contract. */
@Component
public class InferenceClient {
    private final RestClient client;
    private final ObjectMapper json;
    private final boolean configured;

    public InferenceClient(ObjectMapper json,
                           @Value("${LAWWIZ_AI_SERVICE_BASE_URL:}") String baseUrl,
                           @Value("${LAWWIZ_AI_SERVICE_TOKEN:}") String token,
                           @Value("${LAWWIZ_AI_SERVICE_TIMEOUT_SECONDS:65}") long timeoutSeconds) {
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(5)).build());
        factory.setReadTimeout(Duration.ofSeconds(timeoutSeconds));
        client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory)
                .defaultHeaders(headers -> headers.setBearerAuth(token)).build();
        configured = !baseUrl.isBlank() && !token.isBlank();
        this.json = json;
    }

    public JsonNode qa(Object payload, String requestId, String traceId) {
        JsonNode result = invoke("qa", payload, requestId, traceId);
        if (result.path("answer").asString("").isBlank() || !result.path("citations").isArray()) {
            throw new ApiError(50201, "AI 服务返回的问答结果不合法");
        }
        return result;
    }

    public JsonNode review(Object payload, String requestId, String traceId) {
        JsonNode result = invoke("review", payload, requestId, traceId);
        if (!result.path("extracted_terms").isObject() || !result.path("risk_points").isArray()) {
            throw new ApiError(50201, "AI 服务返回的审查结果不合法");
        }
        return result;
    }

    private JsonNode invoke(String operation, Object payload, String requestId, String traceId) {
        if (!configured) {
            throw new ApiError(50301, "模型服务未配置");
        }
        try {
            JsonNode requestBody = json.valueToTree(payload);
            JsonNode result = client.post().uri("/internal/" + operation)
                    .header("X-Request-ID", requestId).header("X-Trace-ID", traceId)
                    .contentType(org.springframework.http.MediaType.APPLICATION_JSON).body(requestBody)
                    .retrieve().body(JsonNode.class);
            if (result == null || !result.isObject()) {
                throw new ApiError(50201, "AI 服务响应结构不合法");
            }
            return result;
        } catch (RestClientResponseException error) {
            throw upstreamError(error);
        } catch (ResourceAccessException error) {
            String message = error.getMostSpecificCause() instanceof java.net.http.HttpTimeoutException
                    ? "AI 推理超时" : "AI 服务暂不可用";
            throw new ApiError(50301, message);
        } catch (RestClientException error) {
            throw new ApiError(50201, "AI 服务响应结构不合法");
        }
    }

    private ApiError upstreamError(RestClientResponseException error) {
        JsonNode body;
        try {
            body = json.readTree(error.getResponseBodyAsString());
        } catch (RuntimeException unreadable) {
            return new ApiError(50301, "AI 服务暂不可用");
        }
        String message = body.path("message").asString("AI 服务暂不可用");
        return switch (body.path("code").asString("")) {
            case "knowledge_not_found" -> new ApiError(40403, message);
            case "knowledge_unavailable" -> new ApiError(50303, message);
            case "invalid_input", "bad_response" -> new ApiError(50201, message);
            case "model_unavailable" -> new ApiError(50301, message);
            default -> new ApiError(50301, "AI 服务暂不可用");
        };
    }
}
