package com.lawwiz.business.auth;

import java.math.BigInteger;
import java.util.Map;

import com.lawwiz.business.api.ApiEnvelope;
import com.lawwiz.business.api.RateLimits;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Expose the existing registration, login, refresh, logout and profile endpoints. */
@RestController
@RequestMapping("/api")
class AuthController {
    record Register(
            @Pattern(regexp = "1[3-9][0-9]{9}") String phone,
            @Size(max = 120) @Pattern(regexp = "[^@\\s]+@[^@\\s]+\\.[^@\\s]+") String email,
            @NotNull @Size(min = 8, max = 64) String password,
            @NotNull @Size(min = 4, max = 8) String verifyCode) {}

    record Login(@NotNull @Size(min = 1, max = 120) String account,
                 @NotNull @Size(min = 1, max = 64) String password) {}

    record Refresh(@NotNull @Size(min = 8, max = 128) String refreshToken) {}

    record Update(@Size(max = 64) String realName, @Size(max = 200) String orgName,
                  @Size(max = 64) String orgRole) {}

    private final AuthService auth;
    private final AccessTokens tokens;
    private final RateLimits limits;
    private final int authLimit;
    private final int readLimit;

    AuthController(AuthService auth, AccessTokens tokens, RateLimits limits,
                   @Value("${LAWWIZ_RATE_LIMIT_AUTH_PER_MINUTE:10}") int authLimit,
                   @Value("${LAWWIZ_RATE_LIMIT_READ_PER_MINUTE:120}") int readLimit) {
        this.auth = auth;
        this.tokens = tokens;
        this.limits = limits;
        this.authLimit = authLimit;
        this.readLimit = readLimit;
    }

    @PostMapping("/auth/register")
    @ResponseStatus(HttpStatus.CREATED)
    ApiEnvelope register(@Valid @RequestBody Register payload, HttpServletRequest request, HttpServletResponse response) {
        limits.require("auth", request.getRemoteAddr(), authLimit, response);
        String userId = auth.register(payload.phone(), payload.email(), payload.password(), payload.verifyCode());
        return ApiEnvelope.success(Map.of("user_id", userId), request);
    }

    @PostMapping("/auth/login")
    ApiEnvelope login(@Valid @RequestBody Login payload, HttpServletRequest request, HttpServletResponse response) {
        limits.require("auth", request.getRemoteAddr(), authLimit, response);
        return ApiEnvelope.success(auth.login(payload.account(), payload.password()), request);
    }

    @PostMapping("/auth/refresh")
    ApiEnvelope refresh(@Valid @RequestBody Refresh payload, HttpServletRequest request, HttpServletResponse response) {
        limits.require("auth", request.getRemoteAddr(), authLimit, response);
        return ApiEnvelope.success(auth.refresh(payload.refreshToken()), request);
    }

    @PostMapping("/auth/logout")
    ApiEnvelope logout(@Valid @RequestBody Refresh payload, HttpServletRequest request, HttpServletResponse response) {
        auth.logout(payload.refreshToken(), user(request, response));
        return ApiEnvelope.success(null, request);
    }

    @GetMapping("/users/me")
    ApiEnvelope current(HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(auth.current(user(request, response)), request);
    }

    @PutMapping("/users/me")
    ApiEnvelope update(@Valid @RequestBody Update payload, HttpServletRequest request, HttpServletResponse response) {
        var profile = new UserMapper.Profile(payload.realName(), payload.orgName(), payload.orgRole());
        return ApiEnvelope.success(auth.update(user(request, response), profile), request);
    }

    private BigInteger user(HttpServletRequest request, HttpServletResponse response) {
        BigInteger id = tokens.requireUser(request.getHeader("Authorization"));
        limits.require("read", id.toString(), readLimit, response);
        return id;
    }
}
