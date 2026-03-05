#[derive(Clone, Debug)]
pub enum MatchCondition {
    Host(String),
    Path(String),
    Method(String),
    Header(String, String),
}

#[derive(Clone, Debug)]
pub struct MatchingRule {
    pub conditions: Vec<MatchCondition>,
    pub policy_name: String,
    pub priority: i32,
}
