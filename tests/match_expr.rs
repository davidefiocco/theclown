fn main() {
    for i in 0..5 {
        let label = match i {
            0 => "zero",
            1 => "one",
            _ => "many",
        };
        println!("{}", label);
    }
}
