package com.lawwiz.business.inference;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.function.Consumer;

import com.lawwiz.business.api.ApiError;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Call the authenticated inference service and translate its failure contract. */
@Component
public class InferenceClient {
    private static final MediaType NDJSON = MediaType.parseMediaType("application/x-ndjson");
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

    /** Forward draft deltas and return only the terminal structured result. */
    public JsonNode qa(Object payload, String requestId, String traceId, Consumer<String> onDelta) {
        try {
            return post("qa/stream", payload, requestId, traceId).accept(NDJSON)
                    .exchange((request, response) -> readAnswer(response, onDelta));
        } catch (ResourceAccessException error) {
            throw serviceUnavailable(error);
        } catch (JacksonException | RestClientException error) {
            throw new ApiError(50201, "AI 服务返回的问答结果不合法");
        }
    }

    public JsonNode review(Object payload, String requestId, String traceId) {
        JsonNode result = invoke("review", payload, requestId, traceId);
        if (!result.path("extracted_terms").isObject() || !result.path("risk_points").isArray()) {
            throw new ApiError(50201, "AI 服务返回的审查结果不合法");
        }
        return result;
    }

    private JsonNode invoke(String operation, Object payload, String requestId, String traceId) {
        try {
            JsonNode result = post(operation, payload, requestId, traceId).retrieve().body(JsonNode.class);
            if (result == null || !result.isObject()) {
                throw new ApiError(50201, "AI 服务响应结构不合法");
            }
            return result;
        } catch (RestClientResponseException error) {
            throw upstreamError(error);
        } catch (ResourceAccessException error) {
            throw serviceUnavailable(error);
        } catch (RestClientException error) {
            throw new ApiError(50201, "AI 服务响应结构不合法");
        }
    }

    private RestClient.RequestBodySpec post(String operation, Object payload, String requestId, String traceId) {
        if (!configured) {
            throw new ApiError(50301, "模型服务未配置");
        }
        JsonNode requestBody = json.valueToTree(payload);
        return client.post().uri("/internal/" + operation)
                .header("X-Request-ID", requestId).header("X-Trace-ID", traceId)
                .contentType(MediaType.APPLICATION_JSON).body(requestBody);
    }

    private JsonNode readAnswer(ClientHttpResponse response, Consumer<String> onDelta) throws IOException {
        if (response.getStatusCode().isError()) {
            throw upstreamError(json.readTree(response.getBody()));
        }
        if (!NDJSON.isCompatibleWith(response.getHeaders().getContentType())) {
            throw new ApiError(50201, "AI 服务问答流格式不合法");
        }
        var reader = new BufferedReader(new InputStreamReader(response.getBody(), StandardCharsets.UTF_8));
        String line;
        while ((line = reader.readLine()) != null) {
            JsonNode event = json.readTree(line);
            switch (event.path("type").asString("")) {
                case "delta" -> onDelta.accept(event.path("text").asString(""));
                case "error" -> throw upstreamError(event);
                case "result" -> {
                    JsonNode result = event.path("result");
                    if (result.path("answer").asString("").isBlank() || !result.path("citations").isArray()) {
                        throw new ApiError(50201, "AI 服务返回的问答结果不合法");
                    }
                    return result;
                }
                default -> throw new ApiError(50201, "AI 服务问答流格式不合法");
            }
        }
        throw new ApiError(50301, "AI 服务问答流已中断");
    }

    private ApiError serviceUnavailable(ResourceAccessException error) {
        String message = error.getMostSpecificCause() instanceof java.net.http.HttpTimeoutException
                ? "AI 推理超时" : "AI 服务暂不可用";
        return new ApiError(50301, message);
    }

    private ApiError upstreamError(RestClientResponseException error) {
        JsonNode body;
        try {
            body = json.readTree(error.getResponseBodyAsString());
        } catch (RuntimeException unreadable) {
            return new ApiError(50301, "AI 服务暂不可用");
        }
        return upstreamError(body);
    }

    private ApiError upstreamError(JsonNode body) {
        if (body == null) {
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
