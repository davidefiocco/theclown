fn tribonacci(n: i32) -> i32 {
    if n == 0 {
        return 0;
    }
    if n <= 2 {
        return 1;
    }
    let mut a = 0;
    let mut b = 1;
    let mut c = 1;
    let mut i = 3;
    while i <= n {
        let tmp = a + b + c;
        a = b;
        b = c;
        c = tmp;
        i = i + 1;
    }
    c
}

fn main() {
    println!("{}", tribonacci(0));
    println!("{}", tribonacci(4));
    println!("{}", tribonacci(10));
}
