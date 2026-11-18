package com.lawwiz.business.api;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Probe the database and cache while preserving the public health response. */
@RestController
class HealthController {
    private final String started = now();
    private final JdbcTemplate jdbc;
    private final StringRedisTemplate redis;
    private final boolean knowledgeConfigured;
    private final boolean aiConfigured;

    HealthController(JdbcTemplate jdbc, StringRedisTemplate redis,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_BASE_URL:}") String knowledgeBaseUrl,
                     @Value("${LAWWIZ_KNOWLEDGE_BASE_SERVICE_KEY:}") String knowledgeBaseToken,
                     @Value("${LAWWIZ_AI_SERVICE_BASE_URL:}") String aiUrl,
                     @Value("${LAWWIZ_AI_SERVICE_TOKEN:}") String aiToken) {
        this.jdbc = jdbc;
        this.redis = redis;
        this.knowledgeConfigured = !knowledgeBaseUrl.isBlank() && !knowledgeBaseToken.isBlank();
        this.aiConfigured = !aiUrl.isBlank() && !aiToken.isBlank();
    }

    @GetMapping("/api/health")
    ApiEnvelope health(HttpServletRequest request) {
        boolean databaseReady = databaseAvailable();
        boolean cacheReady = cacheAvailable();
        var components = Map.of(
                "database", databaseReady ? "ok" : "unavailable",
                "redis", cacheReady ? "ok" : "unavailable",
                "knowledge_base", knowledgeConfigured ? "configured" : "not_configured",
                "ai_service", aiConfigured ? "configured" : "not_configured");
        var payload = Map.of(
                "status", databaseReady ? (cacheReady ? "ok" : "degraded") : "unavailable",
                "components", components,
                "runtime", Map.of("java_version", Runtime.version().toString(), "started_at", started),
                "version", "0.1.0",
                "checked_at", now());
        if (!databaseReady) {
            throw new ApiError(50300, "数据库不可用，服务暂时无法处理请求", payload);
        }
        return ApiEnvelope.success(payload, request);
    }

    private boolean databaseAvailable() {
        try {
            return Integer.valueOf(1).equals(jdbc.queryForObject("SELECT 1", Integer.class));
        } catch (DataAccessException error) {
            return false;
        }
    }

    private boolean cacheAvailable() {
        try {
            return "PONG".equals(redis.execute((RedisCallback<String>) connection -> connection.ping()));
        } catch (DataAccessException error) {
            return false;
        }
    }

    private static String now() {
        return ApiValues.timestamp(LocalDateTime.now(ZoneOffset.ofHours(8)));
    }
}
