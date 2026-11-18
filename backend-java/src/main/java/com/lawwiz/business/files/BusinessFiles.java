package com.lawwiz.business.files;

import java.io.IOException;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Semaphore;
import java.util.function.BiConsumer;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

/** Enforce upload bounds and metadata permissions around content-addressed storage. */
@Service
public class BusinessFiles {
    private static final Logger LOGGER = LoggerFactory.getLogger(BusinessFiles.class);
    public record Source(String bucket, String key, String name, String mime) {}

    private final FileMapper files;
    private final ObjectStorage storage;
    private final TransactionTemplate transactions;
    private final long maxUpload;
    private final long byteQuota;
    private final long numberQuota;
    private final Semaphore uploadSlots = new Semaphore(2);

    BusinessFiles(FileMapper files, ObjectStorage storage, TransactionTemplate transactions,
                  @Value("${LAWWIZ_MAX_UPLOAD_BYTES:20971520}") long maxUpload,
                  @Value("${LAWWIZ_UPLOAD_QUOTA_BYTES_PER_USER:209715200}") long byteQuota,
                  @Value("${LAWWIZ_UPLOAD_QUOTA_FILES_PER_USER:50}") long numberQuota) {
        this.files = files;
        this.storage = storage;
        this.transactions = transactions;
        this.maxUpload = maxUpload;
        this.byteQuota = byteQuota;
        this.numberQuota = numberQuota;
    }

    Map<String, Object> upload(BigInteger owner, MultipartFile upload) {
        if (upload.isEmpty()) {
            throw new ApiError(40001, "文件内容为空");
        }
        if (upload.getSize() > maxUpload) {
            throw new ApiError(41301, "文件超过大小上限");
        }
        if (!uploadSlots.tryAcquire()) {
            throw new ApiError(42901, "服务繁忙，请稍后重试");
        }
        Path temporary = null;
        try {
            Path staged = Files.createTempFile("lawwiz-upload-", ".bin");
            temporary = staged;
            upload.transferTo(staged);
            String mime = FileFormats.identify(staged).mimeType();
            return save(owner, safeName(upload.getOriginalFilename()), mime, ContentKeys.sha256(staged),
                    Files.size(staged), true, (bucket, key) -> storage.put(bucket, key, staged, mime));
        } catch (IOException error) {
            throw new ApiError(50000, "无法读取上传文件");
        } finally {
            if (temporary != null) {
                try {
                    Files.deleteIfExists(temporary);
                } catch (IOException error) {
                    LOGGER.warn("Could not remove upload temporary file");
                }
            }
            uploadSlots.release();
        }
    }

    public BigInteger saveReport(BigInteger owner, String name, byte[] pdf) {
        String mime = "application/pdf";
        var file = save(owner, name, mime, ContentKeys.sha256(pdf), pdf.length, false,
                (bucket, key) -> storage.put(bucket, key, pdf, mime));
        return ApiValues.id((String) file.get("file_id"));
    }

    public Source source(BigInteger fileId) {
        return source(requireFile(fileId));
    }

    /** Lock a file until the caller has committed the business record that references it. */
    @Transactional(propagation = Propagation.MANDATORY)
    public Source lockSource(BigInteger fileId) {
        var record = files.lock(fileId);
        if (record == null || record.purgeRequestedAt() != null) {
            throw new ApiError(40404, "文件不存在");
        }
        return source(record);
    }

    private Source source(FileMapper.StoredFile record) {
        return new Source(record.storageBucket(), record.objectKey(), record.originalName(), record.mimeType());
    }

    /** Reserve an unreferenced owned file for deletion in the caller's transaction. */
    @Transactional(propagation = Propagation.MANDATORY)
    public boolean retire(BigInteger owner, BigInteger id) {
        var file = files.lock(id);
        return file != null && owner.equals(file.uploaderId()) && files.retire(owner, id) == 1;
    }

    /** Try removal after commit, leaving a durable retirement marker on storage failure. */
    public void purgeRetired(BigInteger id) {
        try {
            transactions.executeWithoutResult(ignored -> {
                var file = files.lock(id);
                if (file != null && file.purgeRequestedAt() != null) removeRetired(file);
            });
        } catch (RuntimeException error) {
            LOGGER.warn("Could not purge retired file {}", id, error);
        }
    }

    @Scheduled(fixedDelay = 60_000, initialDelay = 60_000)
    void purgePending() {
        files.pendingPurges().forEach(this::purgeRetired);
    }

    private void removeRetired(FileMapper.StoredFile file) {
        storage.remove(file.storageBucket(), file.objectKey());
        files.forgetRetired(file.id());
    }

    public byte[] read(Source source) {
        return storage.read(source.bucket(), source.key());
    }

    Map<String, Object> metadata(BigInteger owner, BigInteger id) {
        var record = requireFile(id);
        if (!owner.equals(record.uploaderId())) {
            throw new ApiError(40301, "无权访问该文件");
        }
        return view(record);
    }

    private Map<String, Object> save(BigInteger owner, String name, String mime, String digest, long size,
                                     boolean checkQuota, BiConsumer<String, String> writeObject) {
        String key = ContentKeys.key(digest);
        var data = new HashMap<String, Object>();
        data.put("digest", digest);
        data.put("bucket", storage.bucket());
        data.put("key", key);
        data.put("name", name);
        data.put("size", size);
        data.put("mime", mime);
        data.put("owner", owner);
        return transactions.execute(ignored -> {
            // Reserve the digest in MySQL before writing so a retired copy cannot delete a concurrent upload.
            boolean fresh = files.reserve(data) == 1;
            var file = files.lockDigest(digest);
            if (file == null) throw new ApiError(50000, "无法保存文件");
            if (file.purgeRequestedAt() != null) {
                removeRetired(file);
                files.reserve(data);
                file = files.lockDigest(digest);
                fresh = true;
            }
            if (fresh) {
                if (checkQuota) {
                    var usage = files.usage(owner);
                    if (usage.bytes() > byteQuota || usage.files() > numberQuota) {
                        throw new ApiError(41301, "存储配额已满");
                    }
                }
                writeObject.accept(storage.bucket(), key);
            } else if (!storage.exists(file.storageBucket(), file.objectKey())) {
                if ("local".equals(file.storageBucket())) {
                    writeObject.accept(storage.bucket(), file.objectKey());
                    files.markMigrated(file.id(), storage.bucket());
                } else {
                    writeObject.accept(file.storageBucket(), file.objectKey());
                }
            }
            return uploadView(file, !fresh);
        });
    }

    private FileMapper.StoredFile requireFile(BigInteger id) {
        var record = files.find(id);
        if (record == null) {
            throw new ApiError(40404, "文件不存在");
        }
        return record;
    }

    private Map<String, Object> uploadView(FileMapper.StoredFile record, boolean duplicate) {
        var data = view(record);
        data.put("is_duplicate", duplicate);
        return data;
    }

    private Map<String, Object> view(FileMapper.StoredFile record) {
        var result = new LinkedHashMap<String, Object>();
        result.put("file_id", record.id().toString());
        result.put("original_name", record.originalName());
        result.put("byte_size", record.byteSize());
        result.put("mime_type", record.mimeType());
        result.put("sha256", record.sha256());
        return result;
    }

    private String safeName(String supplied) {
        String name = supplied == null ? "" : supplied.replace('\\', '/');
        String last = name.substring(name.lastIndexOf('/') + 1).strip();
        return last.isEmpty() ? "未命名文件" : ApiValues.limit(last, 255);
    }
}
