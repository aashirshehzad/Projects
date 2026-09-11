/*
 * Deliberately insecure sample for exercising the Java side of the auditor.
 * Every block is labelled with the rule it should trigger. The SAFE block at
 * the bottom must produce NO findings.
 *
 * Try it:
 *   python -m app.main audit examples/insecure_demo.java --no-llm
 * Or drop this file (zipped) into the web UI.
 */
import java.io.ObjectInputStream;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.Random;
import javax.crypto.Cipher;

public class InsecureDemo {

    // ===== JAVA-003 -- Hardcoded secret assignment (HIGH) =====
    private String dbPassword = "hunter2_not_a_real_password";   // JAVA-003
    private String apiKey;

    void setup() {
        apiKey = "abcd1234efgh5678ijkl9012";                      // JAVA-003
    }

    // ===== JAVA-001 -- Unsafe deserialization (CRITICAL) =====
    Object loadSession(ObjectInputStream in) throws Exception {
        return in.readObject();                                    // JAVA-001
    }

    // ===== JAVA-002 -- SQL built with string concatenation (HIGH) =====
    void findUser(Statement stmt, String userId) throws Exception {
        stmt.executeQuery("SELECT * FROM users WHERE id = " + userId);  // JAVA-002
    }

    // ===== JAVA-004 -- Command injection (HIGH) =====
    void runCommand(String userCommand) throws Exception {
        Runtime.getRuntime().exec(userCommand);                     // JAVA-004
    }

    // ===== JAVA-005 -- Weak cryptography (MEDIUM) =====
    byte[] hashPassword(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");        // JAVA-005
        return md.digest(data);
    }

    void encrypt() throws Exception {
        Cipher c = Cipher.getInstance("AES/ECB/PKCS5Padding");      // JAVA-005
    }

    // ===== JAVA-006 -- Insecure randomness for a secret (MEDIUM) =====
    int makeSessionToken() {
        int sessionToken = new Random().nextInt();                  // JAVA-006
        return sessionToken;
    }

    // ===== SAFE -- these must produce NO findings (false-positive check) =====
    private String dbPasswordEnv = System.getenv("DB_PASSWORD");    // safe: not a literal
    private String publicKeyPath = "/etc/keys/public.pem";          // safe: name excluded

    Object safeLoadSession(String json) throws Exception {
        return new com.fasterxml.jackson.databind.ObjectMapper()
                .readValue(json, Object.class);                     // safe: JSON, not readObject
    }

    void safeFindUser(PreparedStatement stmt, String userId) throws Exception {
        stmt.setString(1, userId);
        stmt.executeQuery();                                         // safe: bound parameter
    }

    void safeRunCommand(String[] args) throws Exception {
        new ProcessBuilder(args).start();                            // safe: no exec(String)
    }

    byte[] safeHash(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");     // safe: strong hash
        return md.digest(data);
    }

    int safeSessionId() {
        SecureRandom random = new SecureRandom();
        return random.nextInt();                                     // safe: CSPRNG
    }
}
