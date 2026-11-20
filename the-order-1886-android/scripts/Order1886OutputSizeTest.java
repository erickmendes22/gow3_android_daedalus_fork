package ro.cobrabm.fexdroid;
public final class Order1886OutputSizeTest {
    private static void expected(int[] actual,int width,int height) {
        if(actual[0]!=width||actual[1]!=height)
            throw new AssertionError(actual[0]+"x"+actual[1]+" != "+width+"x"+height);
    }
    public static void main(String[] args) {
        expected(Order1886OutputSize.forSurface(2688,1216,1280),1280,720);
        expected(Order1886OutputSize.forSurface(2688,1216,1600),1600,900);
        expected(Order1886OutputSize.forSurface(2688,1216,1920),1920,1080);
        expected(Order1886OutputSize.forSurface(1920,1080,1280),1280,720);
        expected(Order1886OutputSize.forSurface(720,480,1280),720,404);
        expected(Order1886OutputSize.forSurface(320,180,1280),320,180);
        expected(Order1886OutputSize.forSurface(2688,1216,1024),1024,576);
        expected(Order1886OutputSize.forSurface(2688,1216,768),768,432);
        expected(Order1886OutputSize.forSurface(2688,1216,640),640,360);
        System.out.println("Order1886OutputSize: nine checks passed");
    }
}
