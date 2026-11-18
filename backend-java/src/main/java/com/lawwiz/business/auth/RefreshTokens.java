package com.lawwiz.business.auth;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Component;

/** Preserve the Redis refresh token format and consume each token at most once. */
@Component
class RefreshTokens {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final RedisScript<Long> SAVE = RedisScript.of("""
            redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
            redis.call('SADD', KEYS[2], ARGV[2])
            redis.call('EXPIRE', KEYS[2], ARGV[3])
            return 1
            """, Long.class);
    private static final RedisScript<Long> REVOKE = RedisScript.of("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                redis.call('DEL', KEYS[1])
                redis.call('SREM', KEYS[2], ARGV[2])
            end
            return 1
            """, Long.class);

    private final StringRedisTemplate redis;
    private final String prefix;
    private final String ttlSeconds;

    RefreshTokens(
            StringRedisTemplate redis,
            @Value("${lawwiz.redis-prefix}") String prefix,
            @Value("${LAWWIZ_REFRESH_TOKEN_TTL_SECONDS:604800}") long ttlSeconds) {
        this.redis = redis;
        this.prefix = prefix;
        this.ttlSeconds = Long.toString(ttlSeconds);
    }

    String issue(BigInteger userId) {
        byte[] entropy = new byte[48];
        RANDOM.nextBytes(entropy);
        String token = "rt_" + Base64.getUrlEncoder().withoutPadding().encodeToString(entropy);
        String digest = digest(token);
        try {
            redis.execute(SAVE, List.of(prefix + "rt:" + digest, prefix + "urt:" + userId),
                    userId.toString(), digest, ttlSeconds);
        } catch (DataAccessException error) {
            throw unavailable();
        }
        return token;
    }

    BigInteger consume(String token) {
        String digest = digest(token);
        try {
            String userId = redis.opsForValue().getAndDelete(prefix + "rt:" + digest);
            if (userId == null) {
                throw new ApiError(40102, "刷新令牌无效或已被撤销");
            }
            removeMembership(userId, digest);
            return ApiValues.id(userId);
        } catch (DataAccessException error) {
            throw unavailable();
        }
    }

    void revoke(String token, BigInteger userId) {
        String digest = digest(token);
        try {
            redis.execute(REVOKE, List.of(prefix + "rt:" + digest, prefix + "urt:" + userId),
                    userId.toString(), digest);
        } catch (DataAccessException ignored) {
            // The token expires naturally when Redis recovers.
        }
    }

    private void removeMembership(String userId, String digest) {
        try {
            redis.opsForSet().remove(prefix + "urt:" + userId, digest);
        } catch (DataAccessException ignored) {
            // Membership is advisory. The token key was already removed.
        }
    }

    private ApiError unavailable() {
        return new ApiError(50000, "登录状态存储不可用，请稍后重试");
    }

    private String digest(String token) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
