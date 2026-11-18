package com.lawwiz.business.auth;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Keep authentication data, token rotation, and masked profiles compatible with existing clients. */
@Service
class AuthService {
    record Tokens(String accessToken, String refreshToken, String tokenType, long expiresIn) {}

    record Profile(String id, String phone, String email, String accountType, String status,
                   String lastLoginAt, String createdAt, UserMapper.Profile profile) {}

    private final UserMapper users;
    private final AccessTokens access;
    private final RefreshTokens refresh;
    private final boolean allowFixedCode;

    AuthService(UserMapper users, AccessTokens access, RefreshTokens refresh,
                @Value("${lawwiz.environment}") String environment,
                @Value("${lawwiz.fixed-code}") boolean fixedCode) {
        if ("production".equals(environment) && fixedCode) {
            throw new IllegalArgumentException("生产环境禁止固定验证码");
        }
        this.users = users;
        this.access = access;
        this.refresh = refresh;
        this.allowFixedCode = fixedCode;
    }

    @Transactional
    public String register(String phone, String email, String password, String code) {
        if (phone == null && email == null) {
            throw new ApiError(40001, "手机号与邮箱至少提供一个");
        }
        if (!password.codePoints().anyMatch(Character::isLetter)
                || !password.codePoints().anyMatch(Character::isDigit)) {
            throw ApiError.field(40001, "password", "密码需同时包含字母与数字");
        }
        if (!allowFixedCode || !"000000".equals(code)) {
            throw ApiError.field(40001, "verify_code", "验证码不正确");
        }
        checkUnique(phone, email);
        Map<String, Object> values = new HashMap<>();
        values.put("phone", phone);
        values.put("email", email);
        values.put("passwordHash", PasswordHashes.encode(password));
        try {
            users.insert(values);
        } catch (DuplicateKeyException error) {
            String index = error.getMostSpecificCause().getMessage().toLowerCase(Locale.ROOT);
            if (index.contains("uk_user_phone")) {
                throw phoneTaken();
            }
            if (index.contains("uk_user_email")) {
                throw emailTaken();
            }
            throw error;
        }
        BigInteger id = ApiValues.id(values.get("id").toString());
        users.createProfile(id);
        return id.toString();
    }

    @Transactional
    public Tokens login(String account, String password) {
        UserMapper.User user = users.findByAccount(account.strip());
        if (user == null || !PasswordHashes.matches(password, user.passwordHash())) {
            throw new ApiError(40903, "账号或密码错误");
        }
        if (!"active".equals(user.status())) {
            throw new ApiError(40904, "账号已被停用");
        }
        users.markLogin(user.id());
        return issue(user.id());
    }

    public Tokens refresh(String token) {
        return issue(refresh.consume(token));
    }

    public void logout(String token, BigInteger id) {
        refresh.revoke(token, id);
    }

    public Profile current(BigInteger id) {
        UserMapper.User user = users.find(id);
        if (user == null) {
            throw new ApiError(40101, "访问令牌无效或已过期");
        }
        return new Profile(id.toString(), maskPhone(user.phone()), maskEmail(user.email()),
                user.accountType(), user.status(), ApiValues.timestamp(user.lastLoginAt()),
                ApiValues.timestamp(user.createdAt()), users.profile(id));
    }

    @Transactional
    public Profile update(BigInteger id, UserMapper.Profile profile) {
        current(id);
        users.updateProfile(id, profile);
        return current(id);
    }

    private Tokens issue(BigInteger id) {
        return new Tokens(access.issue(id), refresh.issue(id), "Bearer", access.expiresIn());
    }

    private void checkUnique(String phone, String email) {
        if (phone != null && users.hasPhone(phone)) {
            throw phoneTaken();
        }
        if (email != null && users.hasEmail(email)) {
            throw emailTaken();
        }
    }

    private ApiError phoneTaken() {
        return ApiError.field(40901, "phone", "该手机号已被注册");
    }

    private ApiError emailTaken() {
        return ApiError.field(40902, "email", "该邮箱已被注册");
    }

    private String maskPhone(String phone) {
        return phone == null || phone.length() < 7 ? phone
                : phone.substring(0, 3) + "****" + phone.substring(phone.length() - 4);
    }

    private String maskEmail(String email) {
        int at = email == null ? -1 : email.indexOf('@');
        if (at < 0 || at == email.length() - 1) {
            return email;
        }
        int dot = email.lastIndexOf('.');
        String domainSuffix = dot > at ? email.substring(dot) : "";
        return email.substring(0, Math.min(at, 1)) + "***@" + email.charAt(at + 1) + "***" + domainSuffix;
    }
}
