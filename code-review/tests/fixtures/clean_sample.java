import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.PreparedStatement;
import com.fasterxml.jackson.databind.ObjectMapper;

public class CleanSample {
    private String passwordEnvVar = System.getenv("APP_PASSWORD");  // safe: not a literal
    private String publicKeyPath = "/etc/keys/public.pem";          // safe: name excluded

    void deserialize(String json) throws Exception {
        Object obj = new ObjectMapper().readValue(json, Object.class);  // safe: JSON, no readObject
    }

    void lookup(PreparedStatement stmt, String userId) throws Exception {
        stmt.setString(1, userId);
        stmt.executeQuery();                                        // safe: no concatenated SQL
    }

    void runCommand(String[] args) throws Exception {
        new ProcessBuilder(args).start();                            // safe: no exec(String)
    }

    void strongHash(byte[] data) throws Exception {
        MessageDigest.getInstance("SHA-256");                        // safe: strong hash
    }

    int makeSessionId() {
        SecureRandom random = new SecureRandom();
        return random.nextInt();                                     // safe: CSPRNG
    }
}
