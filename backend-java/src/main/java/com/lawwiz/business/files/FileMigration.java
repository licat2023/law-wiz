package com.lawwiz.business.files;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

/** Check, copy, or roll back file locations after validating both copies against MySQL metadata. */
@Component
@ConditionalOnProperty(name = "lawwiz.file-migration")
class FileMigration implements ApplicationRunner {
    private final FileMapper files;
    private final ObjectStorage storage;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    FileMigration(FileMapper files, ObjectStorage storage, TransactionTemplate transactions, ObjectMapper json) {
        this.files = files;
        this.storage = storage;
        this.transactions = transactions;
        this.json = json;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        String mode = arguments.getOptionValues("lawwiz.file-migration").getFirst();
        if ("initialize".equals(mode)) {
            storage.initializeBucket();
            return;
        }
        if (!List.of("check", "copy", "rollback").contains(mode)) {
            throw new IllegalArgumentException("Expected initialize, check, copy or rollback");
        }
        if (!"check".equals(mode)) {
            storage.initializeBucket();
        }
        BigInteger after = BigInteger.ZERO;
        var updates = new ArrayList<FileMapper.StoredFile>();
        int checked = 0;
        int failures = 0;
        while (true) {
            var batch = files.migrationBatch(after);
            if (batch.isEmpty()) {
                break;
            }
            for (var file : batch) {
                after = file.id();
                try {
                    process(file, mode, updates);
                    checked++;
                    log(file, "verified");
                } catch (RuntimeException error) {
                    failures++;
                    log(file, Objects.toString(error.getMessage(), "verification failed"));
                }
            }
        }
        if (failures > 0) {
            throw new IllegalStateException("验证失败 " + failures + " 个对象，数据库定位未切换");
        }
        if (!updates.isEmpty()) {
            String destination = "rollback".equals(mode) ? "local" : storage.bucket();
            transactions.executeWithoutResult(status -> {
                for (var file : updates) {
                    if (files.changeLocation(file.id(), file.storageBucket(), destination) != 1) {
                        throw new IllegalStateException("File location changed during migration: " + file.id());
                    }
                }
            });
        }
        System.out.println("Verified " + checked + " objects, switched " + updates.size() + " locations");
    }

    private void process(FileMapper.StoredFile file, String mode, List<FileMapper.StoredFile> updates) {
        if (!ContentKeys.key(file.sha256()).equals(file.objectKey())) {
            throw new IllegalStateException("object key disagrees with hash");
        }
        var bytes = storage.read(file.storageBucket(), file.objectKey());
        verify(file, bytes);
        boolean local = "local".equals(file.storageBucket());
        if ("copy".equals(mode) && local) {
            storage.put(file.objectKey(), bytes, file.mimeType() == null ? "application/octet-stream" : file.mimeType());
            verify(file, storage.read(storage.bucket(), file.objectKey()));
            updates.add(file);
        } else if ("rollback".equals(mode) && !local) {
            storage.writeLegacy(file.objectKey(), bytes);
            verify(file, storage.read("local", file.objectKey()));
            updates.add(file);
        }
    }

    private void verify(FileMapper.StoredFile file, byte[] bytes) {
        if (file.byteSize() != bytes.length || !file.sha256().equals(ContentKeys.sha256(bytes))) {
            throw new IllegalStateException("size or SHA-256 mismatch");
        }
    }

    private void log(FileMapper.StoredFile file, String status) {
        System.out.println(json.createObjectNode().put("file_id", file.id().toString())
                .put("key", file.objectKey()).put("sha256", file.sha256()).put("status", status));
    }
}
