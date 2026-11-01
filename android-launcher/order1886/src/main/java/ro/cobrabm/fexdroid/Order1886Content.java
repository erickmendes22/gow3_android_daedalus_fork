package ro.cobrabm.fexdroid;

import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.provider.MediaStore;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;

/** Native, in-place extraction of personally supplied PS4 PKGs. No fake installs or PKG copies. */
final class Order1886Content {
    interface Progress { void update(String text); }
    private static final Pattern TITLE=Pattern.compile("(?im)^\\s*Title ID:\\s*(CUSA[0-9]{5})\\s*$");
    private static final Set<String> EDITIONS=new HashSet<>(Arrays.asList(
        "CUSA00076","CUSA00035","CUSA00070","CUSA00100","CUSA00670","CUSA00785"));
    private final Context context;
    Order1886Content(Context context) { this.context=context; }

    private File extractor() {
        return new File(context.getApplicationInfo().nativeLibraryDir, "liborder1886_pkg_util.so");
    }
    boolean available() { return extractor().isFile(); }

    private static boolean under(File file, File parent) throws IOException {
        return file.getCanonicalPath().startsWith(parent.getCanonicalPath()+File.separator);
    }
    static File localDocument(Context context, Uri uri, boolean directory) throws Exception {
        if ("file".equals(uri.getScheme())) {
            File f=new File(uri.getPath()).getCanonicalFile();
            if (under(f,new File("/storage"))) return f;
            throw new IOException("Arquivo fora do armazenamento permitido.");
        }
        File resolved;
        if ("com.android.externalstorage.documents".equals(uri.getAuthority())) {
            String id=directory ? DocumentsContract.getTreeDocumentId(uri)
                                : DocumentsContract.getDocumentId(uri);
            int colon=id.indexOf(':');
            if(colon<1) throw new IOException("Documento SAF inválido.");
            String volume=id.substring(0,colon);
            String relative=id.substring(colon+1);
            File root;
            if ("primary".equalsIgnoreCase(volume)) root=Environment.getExternalStorageDirectory();
            else {
                if(!volume.matches("[A-Za-z0-9_-]{4,24}"))
                    throw new IOException("Volume de armazenamento não reconhecido");
                root=new File("/storage",volume);
            }
            resolved=new File(root,relative).getCanonicalFile();
            if(!under(resolved,root.getCanonicalFile()) && !resolved.equals(root.getCanonicalFile()))
                throw new IOException("Caminho de armazenamento inválido");
        } else if (!directory) {
            String name=null;
            try {
                String id=DocumentsContract.getDocumentId(uri);
                if(id.startsWith("raw:")) name=id.substring(4);
            } catch(Exception ignored){}
            if(name==null) {
                try (android.database.Cursor cursor=context.getContentResolver().query(
                      uri,new String[]{MediaStore.MediaColumns.DATA},null,null,null)) {
                    if(cursor!=null && cursor.moveToFirst()) name=cursor.getString(0);
                }
            }
            if(name==null) throw new IOException("Selecione um PKG no armazenamento local (não nuvem).");
            resolved=new File(name).getCanonicalFile();
        } else throw new IOException("Selecione uma pasta local no gerenciador de arquivos.");
        File storage=new File("/storage").getCanonicalFile();
        if(!under(resolved,storage)) throw new IOException("O arquivo deve estar no armazenamento local.");
        return resolved;
    }
    private static String sfoTitle(File file) throws IOException {
        if(!file.isFile() || file.length()>1024*1024) throw new IOException("param.sfo ausente/inválido");
        byte[] bytes=new byte[(int)file.length()];
        try(FileInputStream f=new FileInputStream(file)){
            int pos=0,n;while(pos<bytes.length&&(n=f.read(bytes,pos,bytes.length-pos))>0)pos+=n;
            if(pos!=bytes.length)throw new EOFException("param.sfo incompleto");
        }
        ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        if(bytes.length<20||b.getInt(0)!=0x46535000) throw new IOException("Assinatura SFO inválida");
        int keys=b.getInt(8), values=b.getInt(12), count=b.getInt(16);
        if(keys<20||values<keys||values>bytes.length||count<1||count>1024)
            throw new IOException("Tabela SFO inválida");
        for(int i=0;i<count;i++){
            int at=20+i*16;
            if(at+16>bytes.length)break;
            int keyAt=keys+(b.getShort(at)&0xffff),len=b.getInt(at+4),valueAt=values+b.getInt(at+12);
            if(keyAt<keys||keyAt>=values||len<0||valueAt<values||valueAt+len>bytes.length)continue;
            int end=keyAt;
            while(end<values && bytes[end]!=0)end++;
            String key=new String(bytes,keyAt,end-keyAt,StandardCharsets.UTF_8);
            if("TITLE_ID".equals(key)){
                String name=new String(bytes,valueAt,len,StandardCharsets.UTF_8).replace("\0","").trim();
                if(name.matches("CUSA[0-9]{5}"))return name;
            }
        }
        throw new IOException("TITLE_ID não encontrado no SFO");
    }

    private String execute(Progress progress, String... args) throws Exception {
        ArrayList<String> command=new ArrayList<>();
        command.add(extractor().getAbsolutePath());
        command.addAll(Arrays.asList(args));
        ProcessBuilder pb=new ProcessBuilder(command).redirectErrorStream(true);
        pb.environment().put("LD_LIBRARY_PATH",context.getApplicationInfo().nativeLibraryDir);
        pb.directory(context.getCacheDir());
        Process p=pb.start();
        StringBuilder output=new StringBuilder();
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8))){
            String line;int count=0;
            while((line=reader.readLine())!=null){
                if(output.length()<20000)output.append(line).append('\n');
                if(++count%150==0)progress.update("Extrator: "+line);
            }
        }
        int rc=p.waitFor();
        if(rc!=0)throw new IOException("orbis-pkg-util terminou com "+rc+": "+output.substring(Math.max(0,output.length()-2400)));
        return output.toString();
    }

    File install(Uri pkgUri,boolean update,File selectedGame,Progress progress) throws Exception {
        if(!available()) throw new IOException("Extrator ARM64 não foi incluído neste APK.");
        File pkg=localDocument(context,pkgUri,false);
        if(!pkg.isFile()||!pkg.canRead()) throw new IOException("PKG não acessível: "+pkg);
        try(FileInputStream in=new FileInputStream(pkg)){
            byte[] magic=new byte[4];
            if(in.read(magic)!=4 || magic[0]!=0x7f || magic[1]!=0x43 || magic[2]!=0x4e || magic[3]!=0x54)
                throw new IOException("Não é um PKG de PS4.");
        }
        progress.update("Lendo identificador do PKG...");
        String info=execute(progress,"info",pkg.getAbsolutePath());
        Matcher match=TITLE.matcher(info);
        if(!match.find())throw new IOException("TITLE_ID não identificado no PKG.");
        String title=match.group(1).toUpperCase(Locale.ROOT);
        if(!EDITIONS.contains(title))
            throw new IOException("Este port aceita somente edições de The Order: 1886. PKG: "+title);
        File destination;
        if(update){
            if(selectedGame==null||!new File(selectedGame,"eboot.bin").isFile())
                throw new IOException("Selecione primeiro um jogo base.");
            String baseTitle=sfoTitle(new File(selectedGame,"sce_sys/param.sfo"));
            if(!title.equals(baseTitle)) throw new IOException("Update "+title+" não corresponde ao jogo "+baseTitle);
            destination=selectedGame.getCanonicalFile();
        } else {
            destination=new File(Environment.getExternalStorageDirectory(),"TheOrder1886/Games/"+title).getCanonicalFile();
            if(destination.exists()){
                String[] contents=destination.list();
                if(contents==null||contents.length>0)throw new IOException("Já existe uma instalação em "+destination+
                        ". Selecione a pasta existente ou esvazie-a antes de reinstalar.");
            }
            if(!destination.isDirectory()&&!destination.mkdirs())
                throw new IOException("Não foi possível criar "+destination);
        }
        if(under(destination,pkg)||under(pkg,destination)||destination.equals(pkg))
            throw new IOException("PKG e pasta de instalação não podem estar aninhados.");
        progress.update("Extraindo "+title+" diretamente para "+destination+" (sem copiar o PKG)...");
        boolean success=false;
        try{
            if(update)execute(progress,"extract",pkg.getAbsolutePath(),"--output",destination.getAbsolutePath(),"--quiet","--force");
            else execute(progress,"extract",pkg.getAbsolutePath(),"--output",destination.getAbsolutePath(),"--quiet");
            String extracted=sfoTitle(new File(destination,"sce_sys/param.sfo"));
            if(!title.equals(extracted)||!new File(destination,"eboot.bin").isFile())
                throw new IOException("Extração incompleta ou arquivos de outro título.");
            success=true;
            progress.update((update?"Atualização instalada: ":"Jogo instalado: ")+title);
            return destination;
        } finally {
            if(!success && !update)
                progress.update("Extração interrompida; pasta parcial preservada para inspeção: "+destination);
        }
    }
}
