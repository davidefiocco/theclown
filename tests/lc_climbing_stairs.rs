fn climb_stairs(n: i32) -> i32 {
    if n <= 2 {
        return n;
    }
    let mut a = 1;
    let mut b = 2;
    let mut i = 3;
    while i <= n {
        let tmp = a + b;
        a = b;
        b = tmp;
        i = i + 1;
    }
    b
}

fn main() {
    println!("{}", climb_stairs(2));
    println!("{}", climb_stairs(5));
    println!("{}", climb_stairs(10));
}
