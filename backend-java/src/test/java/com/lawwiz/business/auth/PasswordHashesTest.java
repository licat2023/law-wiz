package com.lawwiz.business.auth;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** Checks compatibility with bcrypt hashes already present in the business database. */
class PasswordHashesTest {
    @Test
    void verifiesPythonBcryptHash() {
        String oldHash = "$2b$12$abcdefghijklmnopqrstuuAucD2hkR6b6XD7Igfr2QobaungTQxGO";
        assertThat(PasswordHashes.matches("示例密码Abc123", oldHash)).isTrue();
        assertThat(PasswordHashes.matches("示例密码Abc124", oldHash)).isFalse();
    }

    @Test
    void preservesPythonUtf8ByteTruncation() {
        String prefix = "字".repeat(23) + "A0";
        String first = prefix + "甲";
        String sameFirst72Bytes = prefix + "申";
        assertThat(PasswordHashes.matches(sameFirst72Bytes, PasswordHashes.encode(first))).isTrue();
    }
}
