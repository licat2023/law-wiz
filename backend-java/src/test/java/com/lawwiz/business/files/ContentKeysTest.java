package com.lawwiz.business.files;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** Protect the legacy object layout used by existing contracts and reports. */
class ContentKeysTest {
    @Test
    void matchesExistingSha256Path() {
        String sha256 = ContentKeys.sha256("hello".getBytes(StandardCharsets.UTF_8));
        assertThat(ContentKeys.key(sha256))
                .isEqualTo("files/2c/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
    }
}
