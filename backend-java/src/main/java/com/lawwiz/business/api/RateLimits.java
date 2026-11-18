package com.lawwiz.business.api;

import java.time.Instant;
import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Component;

/** Apply the existing fixed-window Redis limits and response headers. */
@Component
public class RateLimits {
    private static final Logger LOGGER = LoggerFactory.getLogger(RateLimits.class);
    private static final RedisScript<Long> COUNT = RedisScript.of("""
            local count = redis.call('INCR', KEYS[1])
            redis.call('EXPIRE', KEYS[1], 65)
            return count
            """, Long.class);

    private final StringRedisTemplate redis;
    private final String prefix;

    public RateLimits(StringRedisTemplate redis, @Value("${lawwiz.redis-prefix}") String prefix) {
        this.redis = redis;
        this.prefix = prefix;
    }

    public void require(String category, String subject, int limit, HttpServletResponse response) {
        long now = Instant.now().getEpochSecond();
        long window = now / 60;
        long count = 0;
        try {
            Long value = redis.execute(COUNT, List.of(prefix + "rl:" + category + ":" + subject + ":" + window));
            count = value == null ? 0 : value;
        } catch (DataAccessException error) {
            LOGGER.warn("Rate limit storage unavailable for {}", category);
        }
        response.setHeader("X-RateLimit-Limit", Integer.toString(limit));
        response.setHeader("X-RateLimit-Remaining", Long.toString(Math.max(limit - count, 0)));
        response.setHeader("X-RateLimit-Reset", Long.toString((window + 1) * 60));
        if (count > limit) {
            response.setHeader("Retry-After", Long.toString((window + 1) * 60 - now));
            throw new ApiError(42901, "操作过于频繁，请稍后再试");
        }
    }
}
