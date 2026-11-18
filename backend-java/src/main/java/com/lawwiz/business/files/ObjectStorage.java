package com.lawwiz.business.files;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.time.Duration;

import com.lawwiz.business.api.ApiError;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.S3Exception;

/** Write content-addressed objects to RustFS and read legacy volume objects during migration. */
@Component
public class ObjectStorage {
    private final S3Client s3;
    private final String bucket;
    private final Path legacyRoot;

    public ObjectStorage(
            @Value("${LAWWIZ_STORAGE_S3_ENDPOINT:}") String endpoint,
            @Value("${LAWWIZ_STORAGE_S3_ACCESS_KEY:}") String accessKey,
            @Value("${LAWWIZ_STORAGE_S3_SECRET_KEY:}") String secretKey,
            @Value("${LAWWIZ_STORAGE_S3_BUCKET:lawwiz-files}") String bucket,
            @Value("${LAWWIZ_STORAGE_LOCAL_ROOT:./.data}") Path legacyRoot) {
        this.bucket = bucket;
        this.legacyRoot = legacyRoot.toAbsolutePath().normalize();
        s3 = endpoint.isBlank() ? null : S3Client.builder()
                .endpointOverride(URI.create(endpoint)).region(Region.US_EAST_1).forcePathStyle(true)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey)))
                .overrideConfiguration(config -> config.apiCallTimeout(Duration.ofSeconds(20))
                        .apiCallAttemptTimeout(Duration.ofSeconds(8)))
                .build();
    }

    public String bucket() {
        return bucket;
    }

    public boolean exists(String location, String key) {
        if ("local".equals(location)) {
            return Files.isRegularFile(legacyPath(key));
        }
        try {
            requireS3().headObject(request -> request.bucket(location).key(key));
            return true;
        } catch (S3Exception error) {
            if (error.statusCode() == 404) {
                return false;
            }
            throw unavailable();
        } catch (SdkException error) {
            throw unavailable();
        }
    }

    public void put(String key, byte[] content, String mimeType) {
        put(bucket, key, content, mimeType);
    }

    void put(String location, String key, byte[] content, String mimeType) {
        try {
            requireS3().putObject(request -> request.bucket(location).key(key).contentType(mimeType),
                    RequestBody.fromBytes(content));
        } catch (SdkException error) {
            throw unavailable();
        }
    }

    public byte[] read(String location, String key) {
        if ("local".equals(location)) {
            try {
                return Files.readAllBytes(legacyPath(key));
            } catch (NoSuchFileException error) {
                throw missing();
            } catch (IOException error) {
                throw unavailable();
            }
        }
        try {
            return requireS3().getObjectAsBytes(request -> request.bucket(location).key(key)).asByteArray();
        } catch (S3Exception error) {
            if (error.statusCode() == 404) {
                throw missing();
            }
            throw unavailable();
        } catch (SdkException error) {
            throw unavailable();
        }
    }

    private Path legacyPath(String key) {
        Path path = legacyRoot.resolve(key).normalize();
        if (!path.startsWith(legacyRoot) || path.equals(legacyRoot)) {
            throw missing();
        }
        return path;
    }

    private S3Client requireS3() {
        if (s3 == null) {
            throw unavailable();
        }
        return s3;
    }

    private ApiError missing() {
        return new ApiError(40404, "文件内容不存在");
    }

    private ApiError unavailable() {
        return new ApiError(50303, "文件存储暂不可用");
    }

    @PreDestroy
    void close() {
        if (s3 != null) {
            s3.close();
        }
    }
}
