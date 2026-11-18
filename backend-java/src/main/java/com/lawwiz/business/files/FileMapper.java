package com.lawwiz.business.files;

import java.math.BigInteger;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** Read and update the existing business file records. */
@Mapper
interface FileMapper {
    String COLUMNS = "id,sha256,storage_bucket,object_key,original_name,byte_size,mime_type,uploader_id,purge_requested_at";

    record StoredFile(BigInteger id, String sha256, String storageBucket, String objectKey,
                      String originalName, long byteSize, String mimeType, BigInteger uploaderId,
                      LocalDateTime purgeRequestedAt) {}
    record Quota(long bytes, long files) {}

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE id = #{id} "
            + "AND deleted_at IS NULL AND purge_requested_at IS NULL")
    StoredFile find(BigInteger id);

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE id = #{id} AND deleted_at IS NULL FOR UPDATE")
    StoredFile lock(BigInteger id);

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE sha256 = #{digest} AND deleted_at IS NULL FOR UPDATE")
    StoredFile lockDigest(String digest);

    @Select("""
            SELECT COALESCE(SUM(byte_size),0) AS bytes, COUNT(*) AS files
            FROM file_object WHERE uploader_id = #{owner} AND deleted_at IS NULL AND purge_requested_at IS NULL
            """)
    Quota usage(BigInteger owner);

    @Insert("""
            INSERT INTO file_object(sha256,storage_bucket,object_key,original_name,byte_size,mime_type,uploader_id)
            VALUES(#{digest},#{bucket},#{key},#{name},#{size},#{mime},#{owner})
            ON DUPLICATE KEY UPDATE updated_at = GREATEST(CURRENT_TIMESTAMP(3), updated_at + INTERVAL 1000 MICROSECOND)
            """)
    // An insert returns 1; the timestamp change takes an exclusive lock and returns 2 for a duplicate.
    int reserve(Map<String, Object> data);

    // These references are checked at the storage boundary before an object becomes unavailable.
    @Update("""
            UPDATE file_object SET purge_requested_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND uploader_id = #{owner} AND deleted_at IS NULL
              AND purge_requested_at IS NULL
              AND NOT EXISTS(SELECT 1 FROM contract_version WHERE file_object_id = #{id})
              AND NOT EXISTS(SELECT 1 FROM review_report WHERE file_object_id = #{id})
              AND NOT EXISTS(SELECT 1 FROM user_profile WHERE avatar_object_id = #{id})
            """)
    int retire(BigInteger owner, BigInteger id);

    @Select("""
            SELECT id FROM file_object WHERE purge_requested_at IS NOT NULL
            ORDER BY purge_requested_at, id LIMIT 20
            """)
    List<BigInteger> pendingPurges();

    @Delete("DELETE FROM file_object WHERE id = #{id} AND purge_requested_at IS NOT NULL")
    void forgetRetired(BigInteger id);

    @Update("""
            UPDATE file_object SET storage_bucket = #{bucket}, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND storage_bucket = 'local'
            """)
    void markMigrated(BigInteger id, String bucket);

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE id > #{after} "
            + "AND purge_requested_at IS NULL ORDER BY id LIMIT 100")
    List<StoredFile> migrationBatch(BigInteger after);

    @Update("""
            UPDATE file_object SET storage_bucket = #{target}, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND storage_bucket = #{source} AND purge_requested_at IS NULL
            """)
    int changeLocation(BigInteger id, String source, String target);
}
