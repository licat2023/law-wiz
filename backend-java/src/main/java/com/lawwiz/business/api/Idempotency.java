package com.lawwiz.business.api;

import java.time.Duration;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** Preserve cached submissions and serialize concurrent duplicates within the business process. */
@Component
public class Idempotency {
    private static final Logger LOGGER = LoggerFactory.getLogger(Idempotency.class);
    private final Object[] stripes = new Object[64];
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final String prefix;

    Idempotency(StringRedisTemplate redis, ObjectMapper json, @Value("${lawwiz.redis-prefix}") String prefix) {
        this.redis = redis;
        this.json = json;
        this.prefix = prefix;
        java.util.Arrays.setAll(stripes, index -> new Object());
    }

    public JsonNode submit(String scope, String header, Supplier<?> create) {
        var key = header == null ? "" : header.strip();
        if (key.isEmpty()) {
            throw new ApiError(40001, "缺少 Idempotency-Key 请求头");
        }
        if (key.length() > 128 || !java.nio.charset.StandardCharsets.US_ASCII.newEncoder().canEncode(key)) {
            throw new ApiError(40001, "Idempotency-Key 格式不合法");
        }
        String redisKey = prefix + "idem:" + scope + ":" + key;
        synchronized (stripes[Math.floorMod(redisKey.hashCode(), stripes.length)]) {
            try {
                String cached = redis.opsForValue().get(redisKey);
                if (cached != null) {
                    return json.readTree(cached);
                }
            } catch (DataAccessException | tools.jackson.core.JacksonException error) {
                LOGGER.warn("Could not read idempotency cache");
            }
            JsonNode result = json.valueToTree(create.get());
            try {
                redis.opsForValue().set(redisKey, json.writeValueAsString(result), Duration.ofHours(24));
            } catch (DataAccessException error) {
                LOGGER.warn("Could not persist idempotency cache");
            }
            return result;
        }
    }
}
