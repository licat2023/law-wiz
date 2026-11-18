package com.lawwiz.business.files;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** Read and update the existing business file records. */
@Mapper
interface FileMapper {
    String COLUMNS = "id,sha256,storage_bucket,object_key,original_name,byte_size,mime_type,uploader_id";

    record StoredFile(BigInteger id, String sha256, String storageBucket, String objectKey,
                      String originalName, long byteSize, String mimeType, BigInteger uploaderId) {}
    record Quota(long bytes, long files) {}

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE id = #{id} AND deleted_at IS NULL")
    StoredFile find(BigInteger id);

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE sha256 = #{digest} AND deleted_at IS NULL")
    StoredFile findByDigest(String digest);

    @Select("""
            SELECT COALESCE(SUM(byte_size),0) AS bytes, COUNT(*) AS files
            FROM file_object WHERE uploader_id = #{owner} AND deleted_at IS NULL
            """)
    Quota usage(BigInteger owner);

    @Insert("""
            INSERT INTO file_object(sha256,storage_bucket,object_key,original_name,byte_size,mime_type,uploader_id)
            VALUES(#{digest},#{bucket},#{key},#{name},#{size},#{mime},#{owner})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void create(Map<String, Object> data);

    @Update("""
            UPDATE file_object SET storage_bucket = #{bucket}, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND storage_bucket = 'local'
            """)
    void markMigrated(BigInteger id, String bucket);

    @Select("SELECT " + COLUMNS + " FROM file_object WHERE id > #{after} ORDER BY id LIMIT 100")
    List<StoredFile> migrationBatch(BigInteger after);

    @Update("""
            UPDATE file_object SET storage_bucket = #{target}, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND storage_bucket = #{source}
            """)
    int changeLocation(BigInteger id, String source, String target);
}
