"""
Lexer for LDmicro C code output.
Tokenizes the C code into a stream of tokens for the parser.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    # Literals
    NUMBER = auto()
    IDENTIFIER = auto()
    STRING = auto()
    
    # Keywords
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    VOID = auto()
    INT = auto()
    CHAR = auto()
    SHORT = auto()
    LONG = auto()
    UNSIGNED = auto()
    SIGNED = auto()
    STATIC = auto()
    CONST = auto()
    TYPEDEF = auto()
    STRUCT = auto()
    RETURN = auto()
    
    # LDmicro specific types
    SWORD = auto()  # Signed word (16-bit)
    SBYTE = auto()  # Signed byte (8-bit)
    
    # Operators
    PLUS = auto()           # +
    MINUS = auto()          # -
    STAR = auto()           # *
    SLASH = auto()          # /
    PERCENT = auto()        # %
    AMPERSAND = auto()      # &
    PIPE = auto()           # |
    CARET = auto()          # ^
    TILDE = auto()          # ~
    EXCLAIM = auto()        # !
    
    # Comparison
    EQ = auto()             # ==
    NE = auto()             # !=
    LT = auto()             # <
    GT = auto()             # >
    LE = auto()             # <=
    GE = auto()             # >=
    
    # Logical
    AND = auto()            # &&
    OR = auto()             # ||
    
    # Assignment
    ASSIGN = auto()         # =
    PLUS_ASSIGN = auto()    # +=
    MINUS_ASSIGN = auto()   # -=
    STAR_ASSIGN = auto()    # *=
    SLASH_ASSIGN = auto()   # /=
    
    # Shift
    LSHIFT = auto()         # <<
    RSHIFT = auto()         # >>
    
    # Delimiters
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    LBRACE = auto()         # {
    RBRACE = auto()         # }
    LBRACKET = auto()       # [
    RBRACKET = auto()       # ]
    SEMICOLON = auto()      # ;
    COMMA = auto()          # ,
    DOT = auto()            # .
    ARROW = auto()          # ->
    
    # Special
    INCREMENT = auto()      # ++
    DECREMENT = auto()      # --
    
    # Preprocessor (we'll mostly skip these)
    HASH = auto()           # #
    
    # End of file
    EOF = auto()
    
    # Comments (we'll skip these during lexing)
    COMMENT = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int
    
    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Lexer error at line {line}, column {column}: {message}")


class Lexer:
    """
    Tokenizer for LDmicro C code.
    Handles the subset of C that LDmicro generates.
    """
    
    KEYWORDS = {
        'if': TokenType.IF,
        'else': TokenType.ELSE,
        'while': TokenType.WHILE,
        'for': TokenType.FOR,
        'void': TokenType.VOID,
        'int': TokenType.INT,
        'char': TokenType.CHAR,
        'short': TokenType.SHORT,
        'long': TokenType.LONG,
        'unsigned': TokenType.UNSIGNED,
        'signed': TokenType.SIGNED,
        'static': TokenType.STATIC,
        'const': TokenType.CONST,
        'typedef': TokenType.TYPEDEF,
        'struct': TokenType.STRUCT,
        'return': TokenType.RETURN,
        # LDmicro types
        'SWORD': TokenType.SWORD,
        'SBYTE': TokenType.SBYTE,
    }
    
    # Two-character operators (must check these first!)
    TWO_CHAR_OPS = {
        '==': TokenType.EQ,
        '!=': TokenType.NE,
        '<=': TokenType.LE,
        '>=': TokenType.GE,
        '&&': TokenType.AND,
        '||': TokenType.OR,
        '<<': TokenType.LSHIFT,
        '>>': TokenType.RSHIFT,
        '++': TokenType.INCREMENT,
        '--': TokenType.DECREMENT,
        '+=': TokenType.PLUS_ASSIGN,
        '-=': TokenType.MINUS_ASSIGN,
        '*=': TokenType.STAR_ASSIGN,
        '/=': TokenType.SLASH_ASSIGN,
        '->': TokenType.ARROW,
    }
    
    # Single-character operators
    SINGLE_CHAR_OPS = {
        '+': TokenType.PLUS,
        '-': TokenType.MINUS,
        '*': TokenType.STAR,
        '/': TokenType.SLASH,
        '%': TokenType.PERCENT,
        '&': TokenType.AMPERSAND,
        '|': TokenType.PIPE,
        '^': TokenType.CARET,
        '~': TokenType.TILDE,
        '!': TokenType.EXCLAIM,
        '<': TokenType.LT,
        '>': TokenType.GT,
        '=': TokenType.ASSIGN,
        '(': TokenType.LPAREN,
        ')': TokenType.RPAREN,
        '{': TokenType.LBRACE,
        '}': TokenType.RBRACE,
        '[': TokenType.LBRACKET,
        ']': TokenType.RBRACKET,
        ';': TokenType.SEMICOLON,
        ',': TokenType.COMMA,
        '.': TokenType.DOT,
        '#': TokenType.HASH,
    }
    
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
    
    @property
    def current_char(self) -> str | None:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek(self, offset: int = 1) -> str | None:
        pos = self.pos + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> str | None:
        char = self.current_char
        self.pos += 1
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
    
    def skip_whitespace(self):
        while self.current_char and self.current_char.isspace():
            self.advance()
    
    def skip_single_line_comment(self):
        # Skip //
        self.advance()
        self.advance()
        while self.current_char and self.current_char != '\n':
            self.advance()
    
    def skip_multi_line_comment(self):
        # Skip /*
        self.advance()
        self.advance()
        while self.current_char:
            if self.current_char == '*' and self.peek() == '/':
                self.advance()  # *
                self.advance()  # /
                return
            self.advance()
        raise LexerError("Unterminated multi-line comment", self.line, self.column)
    
    def read_number(self) -> Token:
        start_line = self.line
        start_col = self.column
        value = ""
        
        # Handle hex numbers
        if self.current_char == '0' and self.peek() in ('x', 'X'):
            value += self.advance()  # 0
            value += self.advance()  # x
            while self.current_char and self.current_char in '0123456789abcdefABCDEF':
                value += self.advance()
        else:
            # Regular decimal
            while self.current_char and self.current_char.isdigit():
                value += self.advance()
            
            # Handle float (though LDmicro rarely uses them)
            if self.current_char == '.' and self.peek() and self.peek().isdigit():
                value += self.advance()  # .
                while self.current_char and self.current_char.isdigit():
                    value += self.advance()
        
        # Handle suffixes like L, U, UL, etc.
        while self.current_char and self.current_char in 'lLuU':
            value += self.advance()
        
        return Token(TokenType.NUMBER, value, start_line, start_col)
    
    def read_identifier(self) -> Token:
        start_line = self.line
        start_col = self.column
        value = ""
        
        while self.current_char and (self.current_char.isalnum() or self.current_char == '_'):
            value += self.advance()
        
        # Check if it's a keyword
        token_type = self.KEYWORDS.get(value, TokenType.IDENTIFIER)
        return Token(token_type, value, start_line, start_col)
    
    def read_string(self) -> Token:
        start_line = self.line
        start_col = self.column
        quote = self.advance()  # Opening quote
        value = ""
        
        while self.current_char and self.current_char != quote:
            if self.current_char == '\\':
                self.advance()  # Backslash
                if self.current_char:
                    # Handle escape sequences
                    escape_chars = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'"}
                    value += escape_chars.get(self.current_char, self.current_char)
                    self.advance()
            else:
                value += self.advance()
        
        if not self.current_char:
            raise LexerError("Unterminated string", start_line, start_col)
        
        self.advance()  # Closing quote
        return Token(TokenType.STRING, value, start_line, start_col)
    
    def read_char_literal(self) -> Token:
        start_line = self.line
        start_col = self.column
        self.advance()  # Opening quote
        
        if self.current_char == '\\':
            self.advance()
            escape_chars = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', "'": "'", '0': '\0'}
            value = escape_chars.get(self.current_char, self.current_char)
            self.advance()
        else:
            value = self.advance()
        
        if self.current_char != "'":
            raise LexerError("Unterminated character literal", start_line, start_col)
        self.advance()  # Closing quote
        
        return Token(TokenType.NUMBER, str(ord(value)), start_line, start_col)
    
    def skip_preprocessor(self):
        """Skip preprocessor directives (we don't need them for simulation)"""
        while self.current_char and self.current_char != '\n':
            self.advance()
    
    def tokenize(self) -> list[Token]:
        """Tokenize the entire source code."""
        while self.current_char:
            # Skip whitespace
            if self.current_char.isspace():
                self.skip_whitespace()
                continue
            
            # Skip comments
            if self.current_char == '/' and self.peek() == '/':
                self.skip_single_line_comment()
                continue
            
            if self.current_char == '/' and self.peek() == '*':
                self.skip_multi_line_comment()
                continue
            
            # Preprocessor directives
            if self.current_char == '#':
                self.skip_preprocessor()
                continue
            
            # Numbers
            if self.current_char.isdigit():
                self.tokens.append(self.read_number())
                continue
            
            # Identifiers and keywords
            if self.current_char.isalpha() or self.current_char == '_':
                self.tokens.append(self.read_identifier())
                continue
            
            # Strings
            if self.current_char == '"':
                self.tokens.append(self.read_string())
                continue
            
            # Character literals
            if self.current_char == "'":
                self.tokens.append(self.read_char_literal())
                continue
            
            # Two-character operators
            two_char = self.current_char + (self.peek() or '')
            if two_char in self.TWO_CHAR_OPS:
                start_line, start_col = self.line, self.column
                self.advance()
                self.advance()
                self.tokens.append(Token(self.TWO_CHAR_OPS[two_char], two_char, start_line, start_col))
                continue
            
            # Single-character operators
            if self.current_char in self.SINGLE_CHAR_OPS:
                start_line, start_col = self.line, self.column
                char = self.advance()
                self.tokens.append(Token(self.SINGLE_CHAR_OPS[char], char, start_line, start_col))
                continue
            
            # Unknown character
            raise LexerError(f"Unexpected character: {self.current_char!r}", self.line, self.column)
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        return self.tokens
    
    def __iter__(self) -> Iterator[Token]:
        if not self.tokens:
            self.tokenize()
        return iter(self.tokens)


def tokenize(source: str) -> list[Token]:
    """Convenience function to tokenize source code."""
    lexer = Lexer(source)
    return lexer.tokenize()

