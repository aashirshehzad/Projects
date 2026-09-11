import java.io.ObjectInputStream;
import java.security.MessageDigest;
import java.sql.Statement;
import java.util.Random;
import javax.crypto.Cipher;

public class VulnerableSample {
    // JAVA-003
    private String password = "hunter2xyz";

    void deserialize(ObjectInputStream in) throws Exception {
        Object obj = in.readObject();                       // JAVA-001
    }

    void lookup(Statement stmt, String userId) throws Exception {
        stmt.executeQuery("SELECT * FROM users WHERE id = " + userId);  // JAVA-002
    }

    void runCommand(String cmd) throws Exception {
        Runtime.getRuntime().exec(cmd);                       // JAVA-004
    }

    void weakHash(byte[] data) throws Exception {
        MessageDigest.getInstance("MD5");                     // JAVA-005
    }

    void weakCipher() throws Exception {
        Cipher.getInstance("AES/ECB/PKCS5Padding");            // JAVA-005
    }

    int makeSessionToken() {
        int sessionToken = new Random().nextInt();             // JAVA-006
        return sessionToken;
    }
}
