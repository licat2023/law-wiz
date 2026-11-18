package com.lawwiz.business.auth;

import java.math.BigInteger;
import java.time.LocalDateTime;
import java.util.Map;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** Map the existing user and profile tables without schema changes. */
@Mapper
interface UserMapper {
    String COLUMNS = "id, phone, email, password_hash, account_type, status, last_login_at, created_at";

    record User(BigInteger id, String phone, String email, String passwordHash, String accountType,
                String status, LocalDateTime lastLoginAt, LocalDateTime createdAt) {}

    record Profile(String realName, String orgName, String orgRole) {}

    @Select("SELECT " + COLUMNS + " FROM user WHERE phone = #{account} OR email = #{account} LIMIT 1")
    User findByAccount(String account);

    @Select("SELECT " + COLUMNS + " FROM user WHERE id = #{id}")
    User find(BigInteger id);

    @Select("SELECT EXISTS (SELECT 1 FROM user WHERE phone = #{phone})")
    boolean hasPhone(String phone);

    @Select("SELECT EXISTS (SELECT 1 FROM user WHERE email = #{email})")
    boolean hasEmail(String email);

    @Insert("INSERT INTO user(phone,email,password_hash) VALUES(#{phone},#{email},#{passwordHash})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void insert(Map<String, Object> values);

    @Insert("INSERT INTO user_profile(user_id) VALUES(#{id})")
    void createProfile(BigInteger id);

    @Select("SELECT real_name, org_name, org_role FROM user_profile WHERE user_id = #{id}")
    Profile profile(BigInteger id);

    @Update("UPDATE user SET last_login_at = CURRENT_TIMESTAMP(3), updated_at = CURRENT_TIMESTAMP(3) WHERE id = #{id}")
    void markLogin(BigInteger id);

    @Insert("""
            INSERT INTO user_profile(user_id, real_name, org_name, org_role)
            VALUES(#{id}, #{profile.realName}, #{profile.orgName}, #{profile.orgRole}) AS incoming
            ON DUPLICATE KEY UPDATE
                  real_name = COALESCE(incoming.real_name, user_profile.real_name),
                  org_name = COALESCE(incoming.org_name, user_profile.org_name),
                  org_role = COALESCE(incoming.org_role, user_profile.org_role),
                  updated_at = CURRENT_TIMESTAMP(3)
            """)
    void updateProfile(BigInteger id, Profile profile);
}
