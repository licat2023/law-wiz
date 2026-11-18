package com.lawwiz.business.auth;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.springframework.security.crypto.bcrypt.BCrypt;

/** Produce and verify the bcrypt hashes used by the Python backend. */
final class PasswordHashes {
    private PasswordHashes() {}

    static String encode(String password) {
        return BCrypt.hashpw(bytes(password), BCrypt.gensalt("$2b", 12));
    }

    static boolean matches(String password, String hash) {
        try {
            return BCrypt.checkpw(bytes(password), hash);
        } catch (IllegalArgumentException error) {
            return false;
        }
    }

    private static byte[] bytes(String password) {
        byte[] encoded = password.getBytes(StandardCharsets.UTF_8);
        return encoded.length <= 72 ? encoded : Arrays.copyOf(encoded, 72);
    }
}
