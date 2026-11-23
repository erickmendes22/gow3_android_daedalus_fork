package ro.cobrabm.fexdroid;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;

/**
 * Real device load observations for the Shadow of the Colossus HUD.
 * CPU = aggregate device busy time from /proc/stat; GPU = KGSL GPU busy time.
 * Unreadable data is NaN -> HUD N/A, never an estimated/fake percentage.
 */
final class SotcLoadSampler {
    private long previousCpuTotal=-1, previousCpuIdle=-1;
    double[] sample() {
        double cpu=Double.NaN,gpu=Double.NaN;
        try (BufferedReader r=new BufferedReader(new FileReader("/proc/stat"))) {
            String line=r.readLine();
            if (line!=null && line.startsWith("cpu ")) {
                String[] fields=line.trim().split("\\s+");
                long total=0,idle=0;
                for(int i=1;i<fields.length;i++){
                    long v=Long.parseLong(fields[i]);
                    total+=v;
                    if(i==4 || i==5)idle+=v;
                }
                if(previousCpuTotal>=0 && total>previousCpuTotal){
                    long dt=total-previousCpuTotal,di=idle-previousCpuIdle;
                    if(di>=0 && di<=dt)cpu=100.0*(dt-di)/dt;
                }
                previousCpuTotal=total;previousCpuIdle=idle;
            }
        } catch(Exception ignored){ /* Android can restrict /proc/stat */ }
        // Qualcomm KGSL exports busy/total microseconds for the recent sample
        // window. Do not substitute current frequency for utilization.
        File busy=new File("/sys/class/kgsl/kgsl-3d0/gpubusy");
        if(busy.isFile()) {
            try(BufferedReader r=new BufferedReader(new FileReader(busy))) {
                String line=r.readLine();
                if(line!=null) {
                    String[] values=line.trim().split("\\s+");
                    if(values.length>=2) {
                        long busyTime=Long.parseLong(values[0]);
                        long totalTime=Long.parseLong(values[1]);
                        if(totalTime>0 && busyTime>=0 && busyTime<=totalTime)
                            gpu=100.0*busyTime/totalTime;
                    }
                }
            } catch(Exception ignored){ /* Display N/A on permission denial */ }
        }
        return new double[]{cpu,gpu};
    }
}
