package com.lawwiz.business.auth;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import javax.crypto.spec.SecretKeySpec;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.stereotype.Component;

/** Issue and validate access tokens with the existing HS256 claims and string subject. */
@Component
public class AccessTokens {
    private final NimbusJwtDecoder decoder;
    private final NimbusJwtEncoder encoder;
    private final Duration lifetime;

    public AccessTokens(
            @Value("${lawwiz.jwt-secret}") String secret,
            @Value("${lawwiz.environment}") String environment,
            @Value("${LAWWIZ_ACCESS_TOKEN_TTL_SECONDS:1800}") long lifetimeSeconds) {
        if (secret.getBytes(StandardCharsets.UTF_8).length < 32
                || ("production".equals(environment) && secret.startsWith("dev-only"))) {
            throw new IllegalArgumentException("需要有效的 JWT 签名密钥");
        }
        var key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
        encoder = new NimbusJwtEncoder(new ImmutableSecret<>(key));
        decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
        lifetime = Duration.ofSeconds(lifetimeSeconds);
    }

    String issue(BigInteger userId) {
        Instant now = Instant.now();
        var claims = JwtClaimsSet.builder()
                .subject(userId.toString())
                .issuedAt(now)
                .expiresAt(now.plus(lifetime))
                .id(UUID.randomUUID().toString().replace("-", ""))
                .claim("typ", "access")
                .build();
        var jws = JwsHeader.with(MacAlgorithm.HS256).type("JWT").build();
        return encoder.encode(JwtEncoderParameters.from(jws, claims)).getTokenValue();
    }

    long expiresIn() {
        return lifetime.toSeconds();
    }

    public BigInteger requireUser(String authorization) {
        try {
            if (authorization == null || !authorization.regionMatches(true, 0, "Bearer ", 0, 7)) {
                throw invalidToken();
            }
            var token = decoder.decode(authorization.substring(7));
            if (!"access".equals(token.getClaimAsString("typ")) || token.getExpiresAt() == null
                    || !token.getExpiresAt().isAfter(Instant.now())) {
                throw invalidToken();
            }
            return ApiValues.id(token.getSubject());
        } catch (RuntimeException error) {
            throw invalidToken();
        }
    }

    private ApiError invalidToken() {
        return new ApiError(40101, "访问令牌无效或已过期");
    }
}
