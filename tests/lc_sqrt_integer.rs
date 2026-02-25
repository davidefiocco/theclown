fn my_sqrt(x: i32) -> i32 {
    if x < 2 {
        return x;
    }
    let mut lo = 1;
    let mut hi = x / 2;
    let mut result = 1;
    while lo <= hi {
        let mid = lo + (hi - lo) / 2;
        if mid <= x / mid {
            result = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    result
}

fn main() {
    println!("{}", my_sqrt(0));
    println!("{}", my_sqrt(4));
    println!("{}", my_sqrt(8));
    println!("{}", my_sqrt(100));
}
